"""Test localhost HTTP/MJPEG behavior without starting LIBERO or saving frames.

Run with ordinary Python; this suite requires only the standard library:
    python docs/W6/rgb_blocks/test_browser_viewer_http.py
"""

import errno
import http.client
import io
import json
import subprocess
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import browser_viewer
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

    def test_existing_legacy_viewer_is_recognized_over_http(self):
        # Keep this FakeSimulation without viewer_id to cover a server that was
        # already running before the duplicate-launch fix was installed.
        self.assertEqual(browser_viewer.probe_existing_viewer(self.port),
                         self.simulation.get_status())

    def test_existing_identified_viewer_is_recognized_over_http(self):
        self.simulation.status["viewer_id"] = browser_viewer.VIEWER_ID
        self.assertEqual(browser_viewer.probe_existing_viewer(self.port),
                         self.simulation.get_status())

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


class ExistingViewerTests(unittest.TestCase):
    """Exercise duplicate launches without starting or killing any simulation."""

    def setUp(self):
        self.status = FakeSimulation().get_status()
        self.status["viewer_id"] = browser_viewer.VIEWER_ID

    def probe_mock_response(self, body, page=PAGE, status_code=200, page_code=200):
        connection = mock.Mock()
        status_response = mock.Mock(status=status_code)
        status_response.read.return_value = body
        page_response = mock.Mock(status=page_code)
        page_response.read.return_value = page
        connection.getresponse.side_effect = [status_response, page_response]
        with mock.patch.object(browser_viewer.http.client, "HTTPConnection",
                               return_value=connection) as constructor:
            result = browser_viewer.probe_existing_viewer(12345, timeout=0.5)
        constructor.assert_called_once_with("127.0.0.1", 12345, timeout=0.5)
        connection.close.assert_called_once_with()
        return result, connection, status_response, page_response

    def probe_status(self, status, **kwargs):
        return self.probe_mock_response(json.dumps(status).encode("utf-8"), **kwargs)

    def run_main_with_bind_error(self, error, existing=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["browser_viewer.py", "--port", "12345"]), \
                mock.patch.object(browser_viewer, "make_server", side_effect=error), \
                mock.patch.object(browser_viewer, "probe_existing_viewer",
                                  return_value=existing) as probe, \
                mock.patch.object(browser_viewer.LiveSimulation, "start") as start, \
                mock.patch.object(browser_viewer.LiveSimulation, "stop") as stop, \
                redirect_stdout(stdout), redirect_stderr(stderr):
            result = browser_viewer.main()
        start.assert_not_called()
        stop.assert_not_called()
        return result, probe, stdout.getvalue(), stderr.getvalue()

    def reuse(self, status):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = browser_viewer.reuse_existing_viewer(status, 12345)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_matching_marker_requires_no_legacy_page_request(self):
        result, connection, status_response, page_response = self.probe_status(self.status)
        self.assertEqual(result, self.status)
        connection.request.assert_called_once_with("GET", "/status")
        status_response.read.assert_called_once_with(65537)
        page_response.read.assert_not_called()

    def test_legacy_viewer_requires_exact_page_match(self):
        status = dict(self.status)
        del status["viewer_id"]
        result, connection, _, page_response = self.probe_status(status)
        self.assertEqual(result, status)
        self.assertEqual(connection.request.call_args_list,
                         [mock.call("GET", "/status"), mock.call("GET", "/")])
        page_response.read.assert_called_once_with(len(PAGE) + 1)

    def test_other_service_or_legacy_page_mismatch_is_not_reused(self):
        different_marker = dict(self.status, viewer_id="another-local-service")
        self.assertIsNone(self.probe_status(different_marker)[0])
        legacy = dict(self.status)
        del legacy["viewer_id"]
        for page in (b"<html>Another application</html>", PAGE + b" ", PAGE[:-1]):
            with self.subTest(page=page[-30:]):
                self.assertIsNone(self.probe_status(legacy, page=page)[0])
        self.assertIsNone(self.probe_status(legacy, page_code=404)[0])

    def test_invalid_json_and_non_dictionary_status_are_rejected(self):
        for body in (b"not JSON", b"", b"\xff", b"[]", b"null", b"123", b"\"status\""):
            with self.subTest(body=body):
                self.assertIsNone(self.probe_mock_response(body)[0])

    def test_missing_fields_or_invalid_status_shape_are_rejected(self):
        required = ("state", "step", "goal", "block_size_mm", "fps", "error",
                    "zero_actions_only", "saved_files", "frame_age_seconds")
        for field in required:
            with self.subTest(missing=field):
                status = dict(self.status)
                del status[field]
                self.assertIsNone(self.probe_status(status)[0])
        for field, value in (
            ("state", "unknown"), ("step", -1), ("step", True), ("step", 7.0),
            ("zero_actions_only", 1), ("zero_actions_only", False),
            ("saved_files", 0), ("saved_files", True),
        ):
            with self.subTest(field=field, value=value):
                self.assertIsNone(self.probe_status(dict(self.status, **{field: value}))[0])

    def test_non_success_http_status_and_oversized_body_are_rejected(self):
        self.assertIsNone(self.probe_status(self.status, status_code=404)[0])
        result, _, response, _ = self.probe_mock_response(b"x" * 65537)
        self.assertIsNone(result)
        response.read.assert_called_once_with(65537)

    def test_connection_failures_return_none_and_close_connection(self):
        for error in (ConnectionRefusedError(), TimeoutError(),
                      http.client.BadStatusLine("bad status")):
            with self.subTest(error=type(error).__name__):
                connection = mock.Mock()
                connection.request.side_effect = error
                with mock.patch.object(browser_viewer.http.client, "HTTPConnection",
                                       return_value=connection):
                    self.assertIsNone(browser_viewer.probe_existing_viewer(12345))
                connection.close.assert_called_once_with()

    def test_duplicate_launch_reuses_healthy_server_without_starting_worker(self):
        result, probe, stdout, stderr = self.run_main_with_bind_error(
            OSError(errno.EADDRINUSE, "Address already in use"), self.status)
        self.assertEqual(result, 0)
        probe.assert_called_once_with(12345)
        self.assertIn("이미 실행 중", stdout)
        self.assertIn("http://localhost:12345", stdout)
        self.assertIn("기존 설정은 유지", stdout)
        self.assertEqual(stderr, "")

    def test_duplicate_launch_does_not_reuse_unrecognized_service(self):
        result, probe, stdout, stderr = self.run_main_with_bind_error(
            OSError(errno.EADDRINUSE, "Address already in use"))
        self.assertEqual(result, 1)
        probe.assert_called_once_with(12345)
        self.assertEqual(stdout, "")
        self.assertIn("Cannot start localhost viewer", stderr)

    def test_non_address_in_use_bind_errors_do_not_probe_or_start_worker(self):
        result, probe, stdout, stderr = self.run_main_with_bind_error(
            OSError(errno.EACCES, "Permission denied"), self.status)
        self.assertEqual(result, 1)
        probe.assert_not_called()
        self.assertEqual(stdout, "")
        self.assertIn("Permission denied", stderr)

    def test_starting_server_is_reused_without_claiming_new_settings(self):
        status = dict(self.status, state="starting", step=0, goal=None,
                      block_size_mm=None, frame_age_seconds=None, fps=0.0)
        result, stdout, stderr = self.reuse(status)
        self.assertEqual(result, 0)
        self.assertIn("기존 화면", stdout)
        self.assertIn("기존 설정은 유지", stdout)
        self.assertEqual(stderr, "")

    def test_error_and_stopped_servers_are_not_announced_as_live(self):
        for status in (
            dict(self.status, state="error", error="MuJoCo initialization failed"),
            dict(self.status, state="stopped"),
            dict(self.status, error="Worker failed"),
        ):
            with self.subTest(state=status["state"], error=status["error"]):
                result, stdout, stderr = self.reuse(status)
                self.assertEqual(result, 1)
                self.assertEqual(stdout, "")
                self.assertIn("정상 실행 상태가 아닙니다", stderr)

    def test_stale_or_invalid_frame_age_is_not_announced_as_live(self):
        for age in (None, True, "0.1", -0.1, 5.01, float("nan"),
                    float("inf"), float("-inf"), 10 ** 1000):
            with self.subTest(age=repr(age)):
                result, stdout, stderr = self.reuse(dict(self.status, frame_age_seconds=age))
                self.assertEqual(result, 1)
                self.assertEqual(stdout, "")
                self.assertIn("화면 갱신이 멈췄습니다", stderr)

    def test_fresh_frame_age_boundaries_are_reused(self):
        for age in (0, 0.0, 5, 5.0):
            with self.subTest(age=age):
                result, stdout, stderr = self.reuse(dict(self.status, frame_age_seconds=age))
                self.assertEqual(result, 0)
                self.assertIn("http://localhost:12345", stdout)
                self.assertEqual(stderr, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
