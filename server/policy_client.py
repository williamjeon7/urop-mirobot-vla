"""HTTP client for :mod:`robot.policy_bridge`; commands are never retried implicitly."""
from __future__ import annotations

import base64
import json
import math
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid

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

    def _request(self, path, payload=None):
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
            with urlopen(request, timeout=self.timeout_s) as response:
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
            suffix = "; command completion is unknown, no automatic retry" if payload is not None else ""
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

    def observation(self):
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
        """Send once. Reusing request_id explicitly retrieves its prior result without motion."""
        request_id = request_id or uuid.uuid4().hex
        result = self._request("/command", {"command": command, "request_id": request_id})
        if result.get("request_id") != request_id or result.get("command") != command or result.get("acknowledged") is not True:
            raise RuntimeError("Bridge acknowledgment does not match the command")
        return result
