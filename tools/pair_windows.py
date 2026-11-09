"""Temporarily pair the Windows USB laptop through VS Code's local port forward.

The one-time bootstrap downloads the current bundle and registers one dedicated
public key. No passwords/private keys are transferred and no robot commands or
recording requests are sent by this service. The OASYS SSH address, user and
port come from config/connection.local.json, which stays out of Git.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import fcntl
import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import struct
import tempfile
import threading
import time

REPO = Path(__file__).resolve().parents[1]
KEY_OPTIONS = ('restrict,port-forwarding,permitlisten="127.0.0.1:8891",'
               'permitopen="127.0.0.1:8891",command="/bin/true"')
CONNECTION = REPO / "config/connection.local.json"


def canonical_key(value):
    if not isinstance(value, str) or "\n" in value or "\r" in value:
        raise ValueError("One ed25519 public key line is required")
    parts = value.strip().split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise ValueError("Only an ed25519 public key is accepted")
    try:
        raw = base64.b64decode(parts[1], validate=True)
        if (len(raw) != 51 or struct.unpack(">I", raw[:4])[0] != 11 or
                raw[4:15] != b"ssh-ed25519" or struct.unpack(">I", raw[15:19])[0] != 32):
            raise ValueError("Malformed ed25519 key")
    except (binascii.Error, struct.error) as error:
        raise ValueError("Malformed ed25519 key") from error
    return "ssh-ed25519 " + base64.b64encode(raw).decode("ascii")


def authorize_key(path, key):
    """Preserve other keys and atomically add a tunnel-only dedicated key."""
    key = canonical_key(key)
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError("authorized_keys is a symlink; automatic enrollment is disabled")
    os.chmod(path.parent, 0o700)
    line = f"{KEY_OPTIONS} {key} mirobot-windows-tunnel\n".encode("ascii")
    descriptor = os.open(path.parent / ".mirobot_pair.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = path.read_bytes() if path.exists() else b""
        if line.strip() in existing.splitlines():
            return
        if existing and not existing.endswith(b"\n"):
            existing += b"\n"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".mirobot_keys_", delete=False) as target:
                temporary = Path(target.name)
                os.chmod(temporary, 0o600)
                target.write(existing + line)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def load_connection(path=CONNECTION):
    """Read the OASYS SSH address/user/port kept out of Git (*.local.json)."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(server_address=str(data["server_address"]), server_user=str(data["server_user"]),
                    ssh_port=int(data["ssh_port"]))
    except FileNotFoundError:
        raise SystemExit(f"{path} is missing: copy config/connection.example.json there and fill in "
                         "the OASYS address, user and SSH port.") from None
    except (KeyError, TypeError, ValueError) as error:
        raise SystemExit(f"{path} needs server_address, server_user and ssh_port ({error}).") from None


class Pairing:
    def __init__(self, archive, authorized_keys, *, host_key, server_address, server_user, ssh_port,
                 ttl=None, rebuild=None):
        self.archive_path = Path(archive)
        self.rebuild = rebuild  # called before each bootstrap so a reused address serves current code
        self.archive = self.archive_path.read_bytes()
        self.archive_hash = hashlib.sha256(self.archive).hexdigest()
        self.authorized_keys = Path(authorized_keys)
        self.host_key = canonical_key(host_key)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", server_address) or not re.fullmatch(r"[A-Za-z0-9_.-]+", server_user):
            raise ValueError("Invalid SSH address/user (check config/connection.local.json)")
        if not isinstance(ssh_port, int) or not 1 <= ssh_port <= 65535:
            raise ValueError("Invalid SSH port (check config/connection.local.json)")
        self.address, self.user, self.ssh_port = server_address, server_user, ssh_port
        self.token = secrets.token_urlsafe(32)
        self.expires = math.inf if ttl is None else time.monotonic() + ttl  # default: until Ctrl+C
        self.lock = threading.Lock()
        self.key = None
        self.keys = set()
        self.phase = "waiting_for_windows"
        self.error = None

    def enroll(self, value):
        key = canonical_key(value)
        with self.lock:
            # Reusable until stopped: each laptop key that installs through this address is authorized.
            authorize_key(self.authorized_keys, key)
            self.keys.add(key)
            self.key = key
            self.phase = "key_registered"
        return {"ok": True}

    def bootstrap(self, host):
        # The request Host preserves the actual Windows forwarded local port.
        if re.fullmatch(r"(?:127\.0\.0\.1|localhost):[0-9]{1,5}", host) is None:
            raise ValueError("Use a localhost port forward")
        if self.rebuild is not None:
            with self.lock:
                self.rebuild(self.archive_path)
                self.archive = self.archive_path.read_bytes()
                self.archive_hash = hashlib.sha256(self.archive).hexdigest()
        template = (REPO / "tools/windows_pair_bootstrap.ps1").read_text(encoding="utf-8")
        values = dict(BASE=f"http://{host}/{self.token}", ARCHIVE_SHA256=self.archive_hash,
                      SSH_ADDRESS=self.address, SSH_USER=self.user, SSH_PORT=str(self.ssh_port),
                      SSH_HOST_KEY=self.host_key)
        for name, value in values.items():
            template = template.replace("__" + name + "__", value.replace("'", "''"))
        return template.encode("utf-8")


def make_handler(pairing):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # URLs contain the temporary pairing capability.

        def send(self, code, body, kind="application/json"):
            if isinstance(body, dict):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def route(self):
            if time.monotonic() >= pairing.expires:
                self.send(HTTPStatus.GONE, {"ok": False, "error": "Pairing expired"})
                return None
            parts = self.path.split("/")
            if len(parts) != 3 or not hmac.compare_digest(parts[1], pairing.token):
                self.send(HTTPStatus.NOT_FOUND, {"ok": False})
                return None
            return parts[2]

        def do_GET(self):
            route = self.route()
            if route is None:
                return
            if route == "bootstrap.ps1":
                try:
                    self.send(HTTPStatus.OK, pairing.bootstrap(self.headers.get("Host", "")), "text/plain; charset=utf-8")
                except ValueError as error:
                    self.send(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
            elif route == "bundle.zip":
                self.send(HTTPStatus.OK, pairing.archive, "application/zip")
            else:
                self.send(HTTPStatus.NOT_FOUND, {"ok": False})

        def do_POST(self):
            route = self.route()
            if route is None:
                return
            if route not in ("enroll", "status"):
                self.send(HTTPStatus.NOT_FOUND, {"ok": False})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("Invalid body length")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("JSON object required")
                if route == "enroll":
                    result = pairing.enroll(data.get("public_key"))
                else:
                    phase = data.get("phase")
                    if phase not in ("downloading", "python_setup", "environment_setup", "bridge_starting", "failed"):
                        raise ValueError("Unknown setup phase")
                    with pairing.lock:
                        pairing.phase = phase
                        pairing.error = str(data.get("error", "")).replace(pairing.token, "[redacted]")[:2000] or None
                    result = {"ok": True}
                self.send(HTTPStatus.OK, result)
            except (ValueError, TypeError, UnicodeError) as error:
                self.send(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
            except (RuntimeError, OSError) as error:
                self.send(HTTPStatus.CONFLICT, {"ok": False, "error": str(error)})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--ttl", type=int, default=None,
                        help="초 단위 유효 시간. 생략하면 Ctrl+C 로 끌 때까지 같은 주소를 계속 쓸 수 있다")
    parser.add_argument("--connection", type=Path, default=CONNECTION,
                        help="JSON with server_address, server_user, ssh_port (kept out of Git)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or (args.ttl is not None and args.ttl < 60):
        parser.error("Valid port and --ttl >= 60 required")
    connection = load_connection(args.connection)
    from tools.package_policy_robot import package
    archive = REPO / "dist/mirobot-policy-robot.zip"
    package(archive)
    pairing = Pairing(archive, Path.home()/".ssh/authorized_keys",
                      host_key=Path("/etc/ssh/ssh_host_ed25519_key.pub").read_text().strip(), ttl=args.ttl,
                      rebuild=package,
                      **connection)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(pairing))
    server.daemon_threads = True
    command = f"irm 'http://127.0.0.1:{args.port}/{pairing.token}/bootstrap.ps1' | iex"
    log_root = REPO / "logs"
    log_root.mkdir(exist_ok=True)
    state = log_root / "windows_pairing.local.json"
    descriptor = os.open(state, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as target:
        json.dump(dict(pid=os.getpid(), port=args.port, command=command, phase=pairing.phase), target)
    print(f"PAIRING_READY port={args.port}; Windows PowerShell command:", flush=True)
    print(command, flush=True)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .2}, daemon=True)
    thread.start()
    previous = None
    try:
        while time.monotonic() < pairing.expires:
            with pairing.lock:
                current = (pairing.phase, pairing.error)
            if current != previous:
                print(json.dumps(dict(phase=current[0], error=current[1]), ensure_ascii=False), flush=True)
                previous = current
            if pairing.key is not None:
                from urllib.request import ProxyHandler, build_opener
                try:
                    with build_opener(ProxyHandler({})).open("http://127.0.0.1:8891/health", timeout=.5) as response:
                        health = json.load(response)
                    if (health.get("ok") is True and health.get("protocol") == "mirobot-policy/1" and
                            health.get("camera", {}).get("serial") == "262422272124"):
                        print('WINDOWS_CONNECTED: robot commands and video were not started. '
                              'The same install command stays usable until Ctrl+C.', flush=True)
                        with pairing.lock:
                            pairing.key = None  # wait for the next install, keep serving
                            pairing.phase = "waiting_for_windows"
                except (OSError, ValueError):
                    pass
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        state.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
