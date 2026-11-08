"""HTTP client for :mod:`robot.policy_bridge`; commands are never retried implicitly."""
from __future__ import annotations

import base64
import json
import math
import os
from pathlib import Path
import re
import shutil
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid

from common.recording_names import valid_recording_name

PROTOCOL = "mirobot-policy/1"


class PolicyClient:
    def __init__(self, base_url: str, timeout_s=40.0, token=None, max_frame_age_s=.5, max_skew_s=.15):
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Bridge URL must be http(s)://host:port")
        if not all(math.isfinite(v) and v > 0 for v in (timeout_s, max_frame_age_s, max_skew_s)):
            raise ValueError("HTTP timeout and observation age limits must be finite positive seconds")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_frame_age_s, self.max_skew_s = max_frame_age_s, max_skew_s
        self.token = token if token is not None else os.environ.get("MIROBOT_POLICY_TOKEN")

    def _request(self, path, payload=None, timeout_s=None):
        headers = {"Accept": "application/json", "Cache-Control": "no-cache"}
        data = None
        if payload is not None:
            data = json.dumps(payload, allow_nan=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = "Bearer "+self.token
        request = Request(self.base_url+path, data=data, headers=headers)
        started = time.monotonic()
        try:
            with urlopen(request, timeout=timeout_s or self.timeout_s) as response:
                raw = response.read(16*1024*1024+1)
                if len(raw) > 16*1024*1024:
                    raise RuntimeError("Bridge response exceeds 16 MiB")
                result = json.loads(raw)
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read(65536)).get("error", str(exc))
            except (ValueError, AttributeError):
                detail = str(exc)
            raise RuntimeError(f"Bridge {path}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            suffix = "; command completion is unknown until resent with the same request_id" if payload is not None else ""
            raise RuntimeError(f"Cannot reach bridge {path}: {exc}{suffix}") from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError(f"Bridge {path} failed: {result.get('error', result) if isinstance(result, dict) else result}")
        result["http_rtt_s"] = time.monotonic()-started
        result["received_monotonic_s"] = time.monotonic()
        return result

    def health(self):
        result = self._request("/health")
        if result.get("protocol") != PROTOCOL:
            raise RuntimeError("Unsupported Mirobot policy bridge protocol")
        return result

    def start_recording(self, run_name=None):
        return self._request("/recording/start", {"run_name": run_name} if run_name else {})

    def recording_names(self):
        names = self._request("/recording/names").get("names")
        if (not isinstance(names, list) or
                any(not valid_recording_name(name) for name in names)):
            raise RuntimeError("Bridge returned invalid recording names")
        return names

    def stop_recording(self):
        return self._request("/recording/stop", {})

    def prepare(self, home=True):
        """home=False: open the gripper and go to the initial pose without homing ($H)."""
        return self._request("/prepare", {"request_id": uuid.uuid4().hex, "home": bool(home)}, timeout_s=300)

    def download_recording(self, name, directory, output_name=None):
        import re
        if not valid_recording_name(name):
            raise ValueError("Recording name must be I1red, I1blue, I1green, ... (legacy I1 also supported)")
        output_name = output_name or name
        if not valid_recording_name(output_name):
            raise ValueError("Invalid local recording name")
        paths = {}
        for kind, suffix in (("video", ".mp4"), ("frames", "_frames.jsonl"), ("metadata", "_video.json")):
            path = Path(directory) / (output_name + suffix)
            temporary = path.with_name(path.name + ".partial")
            headers = {"Authorization": "Bearer " + self.token} if self.token else {}
            request = Request(self.base_url + f"/recording/{name}/{kind}", headers=headers)
            owned = False
            try:
                with urlopen(request, timeout=self.timeout_s) as source, temporary.open("xb") as target:
                    owned = True
                    shutil.copyfileobj(source, target, length=65536)
                    expected = source.headers.get("Content-Length")
                    if expected is None or target.tell() != int(expected):
                        raise RuntimeError(f"Incomplete recording download: {kind}")
                os.link(temporary, path)  # atomic, cannot overwrite an existing file
            finally:
                if owned:
                    temporary.unlink(missing_ok=True)
            paths[kind] = str(path)
        return paths

    # Network hiccups must not end a run: transient errors are retried for up to this long.
    RETRY_BUDGET_S = 15.0
    RETRY_PAUSE_S = 0.1

    def _retrying(self, call, transient, counter):
        deadline = time.monotonic() + self.RETRY_BUDGET_S
        while True:
            try:
                return call()
            except RuntimeError as error:
                if not transient(str(error)) or time.monotonic() >= deadline:
                    raise
                setattr(self, counter, getattr(self, counter, 0) + 1)
                time.sleep(self.RETRY_PAUSE_S)

    def observation(self):
        """Late frames and dropped connections are fetched again (read-only, always safe)."""
        return self._retrying(
            self._observation_once,
            lambda text: "stale" in text.lower() or text.startswith("Cannot reach bridge"),
            "stale_retries")

    def _observation_once(self):
        import cv2
        import numpy as np

        result = self._request("/observation")
        if result.get("protocol") != PROTOCOL:
            raise RuntimeError("Unsupported Mirobot policy bridge protocol")
        if result.get("fault"):
            raise RuntimeError(f"Bridge robot fault: {result['fault']}")
        cart = result.get("cart6")
        if (not isinstance(cart, list) or len(cart) != 6
                or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in cart)
                or not isinstance(result.get("closure"), (float, int))
                or not math.isfinite(result["closure"]) or not 0 <= result["closure"] <= 1):
            raise RuntimeError("Bridge returned invalid Cartesian/gripper observation")
        values = [result.get(key) for key in ("frame_age_s", "state_age_s", "frame_state_skew_s")]
        if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in values):
            raise RuntimeError("Bridge returned invalid observation timing")
        frame_age, state_age, skew = values
        # Bridge and server monotonic clocks have different origins: use remote ages plus RTT.
        if min(frame_age, state_age) < 0 or max(frame_age, state_age)+result["http_rtt_s"] > self.max_frame_age_s or abs(skew) > self.max_skew_s:
            raise RuntimeError("Camera/robot observation is stale or unsynchronized")
        camera = result.get("camera", {})
        if camera.get("encoding") != "png" or camera.get("color_order") != "RGB" or camera.get("preprocessing") != "none":
            raise RuntimeError("Expected an unprocessed, lossless RGB camera frame")
        try:
            encoded = base64.b64decode(result.pop("image_rgb_png_base64"), validate=True)
        except (KeyError, ValueError) as exc:
            raise RuntimeError("Invalid bridge PNG payload") from exc
        bgr = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None or bgr.shape != (camera.get("height"), camera.get("width"), 3):
            raise RuntimeError("Bridge PNG shape differs from camera metadata")
        result["rgb"] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return result

    def command(self, command: str, request_id=None):
        """Send a command; on a dropped connection resend with the SAME request_id.

        The bridge never executes a request_id twice (it returns the first result), so resending is
        safe. "Robot must be Idle" is refused before anything is sent to the arm, so it is retried too.
        """
        request_id = request_id or uuid.uuid4().hex
        result = self._retrying(
            lambda: self._request("/command", {"command": command, "request_id": request_id}),
            lambda text: text.startswith("Cannot reach bridge") or "Robot must be Idle" in text,
            "command_retries")
        if result.get("request_id") != request_id or result.get("command") != command or result.get("acknowledged") is not True:
            raise RuntimeError("Bridge acknowledgment does not match the command")
        return result
