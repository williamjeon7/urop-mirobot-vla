"""Check pairing authentication and key enrollment using temporary files only."""
import base64
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import struct
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

import pytest

from tools.pair_windows import KEY_OPTIONS, Pairing, authorize_key, canonical_key, make_handler


def key(seed=1):
    raw = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + bytes([seed])*32
    return "ssh-ed25519 " + base64.b64encode(raw).decode("ascii")


@pytest.mark.parametrize("value", [None, "", "ssh-rsa AAAA", key() + "\ncommand=bad", key() + "\r", "ssh-ed25519 !!!!", "ssh-ed25519 AAAA"])
def test_enrollment_rejects_malformed_or_injected_keys(value):
    with pytest.raises(ValueError):
        canonical_key(value)


def test_key_registration_preserves_existing_keys_and_is_idempotent(tmp_path):
    target = tmp_path / ".ssh/authorized_keys"
    target.parent.mkdir()
    original = b'ssh-ed25519 previous-public-key old-device'
    target.write_bytes(original)
    authorize_key(target, key() + " notebook")
    first = target.read_bytes()
    authorize_key(target, key() + " different-comment")
    assert target.read_bytes() == first
    assert first.startswith(original + b"\n")
    assert (KEY_OPTIONS + " " + key()).encode() in first
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.parent.stat().st_mode & 0o777 == 0o700


def test_symlinked_authorized_keys_is_not_replaced(tmp_path):
    actual = tmp_path / "managed_keys"
    actual.write_text("original")
    link = tmp_path / "authorized_keys"
    link.symlink_to(actual)
    with pytest.raises(RuntimeError, match="symlink"):
        authorize_key(link, key())
    assert link.is_symlink() and actual.read_text() == "original"


@contextmanager
def service(tmp_path):
    archive = tmp_path / "bundle.zip"
    archive.write_bytes(b"test ZIP snapshot")
    pairing = Pairing(archive, tmp_path / ".ssh/authorized_keys", host_key=key(10))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(pairing))
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    worker.start()
    opener = build_opener(ProxyHandler({}))
    base = f"http://127.0.0.1:{server.server_port}"
    def request(path, body=None):
        payload = json.dumps(body).encode() if body is not None else None
        return opener.open(Request(base + path, data=payload, headers={"Content-Type": "application/json"}), timeout=2)
    try:
        yield pairing, request
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_unauthenticated_requests_cannot_download_or_register_key(tmp_path):
    with service(tmp_path) as (pairing, request):
        for path, body in (("/wrong/bundle.zip", None), ("/wrong/bootstrap.ps1", None),
                           ("/wrong/enroll", {"public_key": key()})):
            with pytest.raises(HTTPError) as error:
                request(path, body)
            assert error.value.code == 404
        assert not pairing.authorized_keys.exists()


def test_enrollment_allows_one_key_and_preserves_download_capability(tmp_path):
    with service(tmp_path) as (pairing, request):
        prefix = "/" + pairing.token
        for _ in range(2):
            with request(prefix + "/enroll", {"public_key": key()}) as response:
                assert json.load(response)["ok"]
        before = pairing.authorized_keys.read_bytes()
        with pytest.raises(HTTPError) as error:
            request(prefix + "/enroll", {"public_key": key(2)})
        assert error.value.code == 409
        assert pairing.authorized_keys.read_bytes() == before
        with request(prefix + "/bundle.zip") as response:
            assert response.read() == pairing.archive


def test_bootstrap_is_bound_to_forwarded_port_and_pins_download_and_host(tmp_path):
    with service(tmp_path) as (pairing, request):
        with request("/" + pairing.token + "/bootstrap.ps1") as response:
            script = response.read().decode("utf-8")
        assert pairing.archive_hash in script and pairing.host_key in script
        assert "__BASE__" not in script and "__SSH_" not in script
        assert "Get-AuthenticodeSignature" in script
        assert "/enroll" in script and "/bundle.zip" in script
        assert "recording/start" not in script
        assert "Invoke-WebRequest" in script


def test_expired_pairing_denies_download_and_enrollment(tmp_path):
    with service(tmp_path) as (pairing, request):
        pairing.expires = time.monotonic() - 1
        for suffix, body in (("bundle.zip", None), ("enroll", {"public_key": key()})):
            with pytest.raises(HTTPError) as error:
                request("/" + pairing.token + "/" + suffix, body)
            assert error.value.code == 410
        assert not pairing.authorized_keys.exists()
