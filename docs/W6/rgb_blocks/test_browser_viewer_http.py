"""Test localhost HTTP/MJPEG behavior without starting LIBERO or saving frames.

Run with ordinary Python; this suite requires only the standard library:
    python docs/W6/rgb_blocks/test_browser_viewer_http.py
"""

import http.client
import json
import subprocess
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from browser_viewer import PAGE, make_server


class FakeSimulation:
    """Supply predictable opaque JPEG bytes without importing simulator packages."""

    def __init__(self):
        self.stop_event = threading.Event()
        self.condition = threading.Condition()
        self.jpeg = b"\xff\xd8fake RGB frame\xff\xd9"
        self.status = {
            "state": "running", "step": 7, "goal": True,
            "block_size_mm": 40.0, "fps": 20.0, "error": None,
            "zero_actions_only": True, "saved_files": False,
            "frame_age_seconds": 0.01,
        }

    def get_status(self):
        with self.condition:
            return dict(self.status)

    def wait_for_frame(self, previous_step, timeout=1.0):
        with self.condition:
            self.condition.wait_for(
                lambda: self.stop_event.is_set() or self.status["error"] is not None
                or (self.jpeg is not None and self.status["step"] != previous_step),
                timeout=timeout,
            )
            if self.jpeg is None or self.status["step"] == previous_step:
                return None
            return self.jpeg, self.status["step"]

    def publish(self, jpeg, step):
        with self.condition:
            self.jpeg = jpeg
            self.status["step"] = step
            self.condition.notify_all()

    def fail_without_frame(self):
        with self.condition:
            self.jpeg = None
            self.status.update(state="error", error="테스트 초기화 오류")
            self.condition.notify_all()

    def stop(self):
        self.stop_event.set()
        with self.condition:
            self.condition.notify_all()


class BrowserViewerHTTPTests(unittest.TestCase):
    def setUp(self):
        self.simulation = FakeSimulation()
        self.server = make_server(self.simulation, port=0)
        self.address, self.port = self.server.server_address
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05},
            daemon=True,
        )
        self.thread.start()

    def tearDown(self):
        self.simulation.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive(), "HTTP server did not stop")

    def request(self, path, method="GET"):
        connection = http.client.HTTPConnection(self.address, self.port, timeout=3)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def stream_connection(self):
        connection = http.client.HTTPConnection(self.address, self.port, timeout=3)
        connection.request("GET", "/stream.mjpg?cache_bust=1")
        return connection, connection.getresponse()

    def read_frame(self, response):
        self.assertEqual(response.readline(), b"--frame\r\n")
        headers = {}
        while True:
            line = response.readline()
            if line == b"\r\n":
                break
            self.assertTrue(line, "Stream ended before the frame headers")
            name, value = line.decode("ascii").strip().split(":", 1)
            headers[name.lower()] = value.strip()
        self.assertEqual(headers["content-type"], "image/jpeg")
        length = int(headers["content-length"])
        jpeg = response.read(length)
        self.assertEqual(len(jpeg), length)
        self.assertEqual(response.read(2), b"\r\n")
        return jpeg

    def test_server_binds_only_loopback_with_ephemeral_port(self):
        self.assertEqual(self.address, "127.0.0.1")
        self.assertGreater(self.port, 0)

    def test_page_is_utf8_and_not_cached(self):
        code, headers, body = self.request("/")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(headers["Content-Length"], str(len(body)))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(body, PAGE)
        self.assertIn("시뮬레이터", body.decode("utf-8"))
        self.assertIn('src="/stream.mjpg"', body.decode("utf-8"))

    def test_page_route_ignores_query_string(self):
        code, _, body = self.request("/?cache_bust=123")
        self.assertEqual(code, 200)
        self.assertEqual(body, PAGE)

    def test_status_is_json_and_not_cached(self):
        code, headers, body = self.request("/status?cache_bust=123")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Content-Length"], str(len(body)))
        self.assertEqual(json.loads(body.decode("utf-8")), self.simulation.get_status())

    def test_unknown_routes_do_not_serve_repository_files(self):
        for path in (
            "/missing", "/objects.py", "/assets/red_block.xml", "/README.md",
            "/../objects.py", "/../../.git/config", "/%2e%2e/README.md",
        ):
            with self.subTest(path=path):
                code, headers, body = self.request(path)
                self.assertEqual(code, 404)
                self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
                self.assertEqual(headers["Cache-Control"], "no-store")
                self.assertEqual(body, b"Not found")

    def test_mjpeg_content_type_lengths_and_successive_frame_bytes(self):
        connection, response = self.stream_connection()
        try:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"),
                             "multipart/x-mixed-replace; boundary=frame")
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
            self.assertEqual(self.read_frame(response), self.simulation.jpeg)
            next_frame = b"\xff\xd8second RGB frame with a different length\xff\xd9"
            self.simulation.publish(next_frame, step=8)
            self.assertEqual(self.read_frame(response), next_frame)
        finally:
            response.close()
            connection.close()

    def test_multiple_status_clients_work_while_stream_remains_open(self):
        connection, response = self.stream_connection()
        try:
            self.assertEqual(self.read_frame(response), self.simulation.jpeg)
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: self.request("/status"), range(16)))
            for code, _, body in results:
                self.assertEqual(code, 200)
                self.assertEqual(json.loads(body.decode("utf-8"))["step"], 7)
        finally:
            response.close()
            connection.close()

    def test_simulator_error_is_visible_and_ends_empty_stream(self):
        self.simulation.fail_without_frame()
        code, _, body = self.request("/status")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body.decode("utf-8"))["error"], "테스트 초기화 오류")
        connection, response = self.stream_connection()
        try:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"")
        finally:
            response.close()
            connection.close()

    def test_browser_module_import_needs_no_simulator_or_opencv(self):
        # A clean interpreter rejects any attempted heavy import before the
        # module loads. The HTTP tests therefore also run outside Conda.
        code = """
import sys
class RejectSimulatorImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'cv2', 'numpy', 'mujoco', 'robosuite', 'libero',
            'preview', 'test_rgb_blocks',
        }:
            raise AssertionError('Unexpected simulator import: ' + fullname)
        return None
sys.meta_path.insert(0, RejectSimulatorImports())
import browser_viewer
assert callable(browser_viewer.make_server)
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=str(Path(__file__).resolve().parent),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
