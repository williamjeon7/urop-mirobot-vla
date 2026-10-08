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
        # Match main(): close the listening socket when serve_forever returns.
        # This also lets shutdown tests verify that the port truly closes.
        def serve_and_close():
            try:
                self.server.serve_forever(poll_interval=0.05)
            finally:
                self.server.server_close()

        self.thread = threading.Thread(target=serve_and_close, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.simulation.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive(), "HTTP server did not stop")

    def request(self, path, method="GET", headers=None):
        connection = http.client.HTTPConnection(self.address, self.port, timeout=3)
        try:
            connection.request(method, path, headers=headers or {})
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
        self.assertNotIn('class="note"', body.decode("utf-8"))
        self.assertNotIn("OASYS에서 실제 물리 시뮬레이션을 실행해", body.decode("utf-8"))

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
        status = json.loads(body.decode("utf-8"))
        token = status.pop("shutdown_token")
        control_token = status.pop("control_token")
        for value in (token, control_token):
            self.assertIsInstance(value, str)
            self.assertGreaterEqual(len(value), 32)
            self.assertTrue(value.isascii())
        self.assertNotEqual(token, control_token)
        self.assertEqual(status, self.simulation.get_status())
        self.assertNotIn("shutdown_token", self.simulation.get_status())

    def control_request(self, body, token=None, host=None, origin=None, raw=None,
                        headers_only=False):
        token = self.status()["control_token"] if token is None else token
        payload = raw if raw is not None else json.dumps(body).encode("utf-8")
        headers = {"X-RGB-Control-Token": token, "Content-Type": "application/json",
                   "Host": host or "localhost:{}".format(self.port)}
        if origin is not None:
            headers["Origin"] = origin
        connection = http.client.HTTPConnection(self.address, self.port, timeout=3)
        try:
            connection.putrequest("POST", "/control", skip_host=True)
            for name, value in headers.items():
                connection.putheader(name, value)
            connection.putheader("Content-Length", str(len(payload)))
            # Header rejections never consume the body. Sending it anyway can make
            # Windows reset the socket before the client receives the rejection.
            connection.endheaders(None if headers_only else payload)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def status(self):
        return json.loads(self.request("/status")[2].decode("utf-8"))

    def test_control_forwards_same_origin_commands_with_token(self):
        received = []
        self.simulation.control = lambda command: received.append(command) or {"ok": True}
        origin = "http://localhost:{}".format(self.port)
        code, body = self.control_request({"action": "pause"}, origin=origin)
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body), {"ok": True})
        code, _ = self.control_request({"action": "play"})   # terminal clients send no Origin
        self.assertEqual(code, 200)
        code, _ = self.control_request({"action": "play"}, host="127.0.0.1:{}".format(self.port))
        self.assertEqual(code, 200)
        self.assertEqual(received, [{"action": "pause"}, {"action": "play"}, {"action": "play"}])

    def test_control_rejects_wrong_token_host_or_origin(self):
        received = []
        self.simulation.control = lambda command: received.append(command) or {"ok": True}
        own = "http://localhost:{}".format(self.port)
        cases = [
            dict(token="wrong-token"),
            dict(token=self.status()["shutdown_token"]),
            dict(token="\u00e9"),
            dict(origin="http://untrusted.example"),
            dict(origin="http://localhost:{}".format(self.port + 1)),
            dict(host="attacker.example:{}".format(self.port),
                 origin="http://attacker.example:{}".format(self.port)),
        ]
        for case in cases:
            with self.subTest(case=case):
                kwargs = dict(origin=own)
                kwargs.update(case)
                code, _ = self.control_request({"action": "pause"}, headers_only=True, **kwargs)
                self.assertEqual(code, 403)
        self.assertEqual(received, [])
        self.assertFalse(self.simulation.stop_event.is_set())

    def test_control_rejects_bad_bodies_and_reports_missing_controls(self):
        code, _ = self.control_request({"action": "pause"})
        self.assertEqual(code, 409)   # FakeSimulation has no controls
        self.simulation.control = lambda command: {"ok": True}
        self.assertEqual(self.control_request(None, raw=b"not json")[0], 400)
        self.assertEqual(self.control_request(["pause"])[0], 400)
        self.assertEqual(self.control_request(
            None, raw=b"{" + b" " * 2000 + b"}", headers_only=True)[0], 413)

        def reject(command):
            raise ValueError("unknown action")
        self.simulation.control = reject
        code, body = self.control_request({"action": "dance"})
        self.assertEqual(code, 400)
        self.assertIn("unknown action", json.loads(body)["error"])

    def test_page_script_strings_do_not_span_lines(self):
        # A raw newline inside a quoted JS string is a syntax error that silently kills
        # the whole status script (10/6 bug). Every line must close its quotes.
        script = PAGE.decode("utf-8").split("<script>", 1)[1].split("</script>", 1)[0]
        for number, line in enumerate(script.splitlines(), 1):
            with self.subTest(line=number):
                self.assertEqual(line.replace("\\'", "").count("'") % 2, 0, line)

    def test_existing_legacy_viewer_is_recognized_over_http(self):
        # Keep this FakeSimulation without viewer_id to cover a server that was
        # already running before the duplicate-launch fix was installed.
        status = browser_viewer.probe_existing_viewer(self.port)
        self.assertTrue(status.pop("shutdown_token"))
        self.assertTrue(status.pop("control_token"))
        self.assertEqual(status, self.simulation.get_status())

    def test_existing_identified_viewer_is_recognized_over_http(self):
        self.simulation.status["viewer_id"] = browser_viewer.VIEWER_ID
        status = browser_viewer.probe_existing_viewer(self.port)
        self.assertTrue(status.pop("shutdown_token"))
        self.assertTrue(status.pop("control_token"))
        self.assertEqual(status, self.simulation.get_status())

    def shutdown_token(self):
        code, _, body = self.request("/status")
        self.assertEqual(code, 200)
        return json.loads(body.decode("utf-8"))["shutdown_token"]

    def test_shutdown_requires_correct_token_and_no_origin(self):
        token = self.shutdown_token()
        for headers in (
            {}, {"X-RGB-Viewer-Token": "wrong-token"},
            {"X-RGB-Viewer-Token": "caf\u00e9"},
            {"X-RGB-Viewer-Token": token, "Origin": "http://untrusted.example"},
            {"X-RGB-Viewer-Token": token, "Origin": ""},
            {"X-RGB-Viewer-Token": token, "Origin": "null"},
        ):
            with self.subTest(headers=list(headers)):
                code, response_headers, body = self.request(
                    "/shutdown", method="POST", headers=headers)
                self.assertEqual(code, 403)
                self.assertEqual(body, b"Forbidden")
                self.assertNotIn("Access-Control-Allow-Origin", response_headers)
                self.assertFalse(self.simulation.stop_event.is_set())
                self.assertEqual(self.request("/status")[0], 200)
        self.assertEqual(self.shutdown_token(), token)

    def test_authenticated_shutdown_stops_server_and_closes_port(self):
        code, headers, body = self.request(
            "/shutdown", method="POST",
            headers={"X-RGB-Viewer-Token": self.shutdown_token()})
        self.assertEqual(code, 202)
        self.assertEqual(json.loads(body.decode("utf-8")), {"stopping": True})
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())
        self.assertTrue(self.simulation.stop_event.is_set())
        self.assertTrue(browser_viewer.wait_for_server_exit(
            self.port, timeout=max(1, browser_viewer.EXIT_PROBE_TIMEOUT)))

    def test_shutdown_client_uses_token_and_server_closes(self):
        self.assertTrue(browser_viewer.request_shutdown(self.port, self.shutdown_token()))
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())
        self.assertTrue(browser_viewer.wait_for_server_exit(
            self.port, timeout=max(1, browser_viewer.EXIT_PROBE_TIMEOUT)))

    def test_get_shutdown_unknown_post_and_preflight_do_not_stop_server(self):
        token = self.shutdown_token()
        code, _, _ = self.request("/shutdown")
        self.assertEqual(code, 404)
        code, _, _ = self.request("/missing", method="POST",
                                  headers={"X-RGB-Viewer-Token": token})
        self.assertEqual(code, 404)
        code, headers, _ = self.request(
            "/shutdown", method="OPTIONS",
            headers={"Origin": "http://untrusted.example",
                     "Access-Control-Request-Method": "POST",
                     "Access-Control-Request-Headers": "X-RGB-Viewer-Token"})
        self.assertEqual(code, 501)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertNotIn("Access-Control-Allow-Headers", headers)
        self.assertFalse(self.simulation.stop_event.is_set())
        self.assertEqual(self.request("/status")[0], 200)

    def test_shutdown_token_is_unique_to_each_server_instance(self):
        first_token = self.shutdown_token()
        other_simulation = FakeSimulation()
        other_server = make_server(other_simulation, port=0)
        other_thread = threading.Thread(
            target=other_server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        other_thread.start()
        try:
            other_status = browser_viewer.probe_existing_viewer(other_server.server_address[1])
            other_token = other_status["shutdown_token"]
            self.assertNotEqual(first_token, other_token)
            code, _, _ = self.request(
                "/shutdown", method="POST", headers={"X-RGB-Viewer-Token": other_token})
            self.assertEqual(code, 403)
            self.assertFalse(self.simulation.stop_event.is_set())
        finally:
            other_simulation.stop()
            other_server.shutdown()
            other_server.server_close()
            other_thread.join(timeout=2)
            self.assertFalse(other_thread.is_alive())

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
        self.status["shutdown_token"] = "test-terminal-shutdown-token"

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
                mock.patch.object(browser_viewer, "follow_existing_viewer",
                                  return_value=0) as follow, \
                redirect_stdout(stdout), redirect_stderr(stderr):
            result = browser_viewer.main()
        start.assert_not_called()
        stop.assert_not_called()
        if result == 0:
            follow.assert_called_once_with(12345, existing["shutdown_token"])
        else:
            follow.assert_not_called()
        return result, probe, stdout.getvalue(), stderr.getvalue()

    def reuse(self, status):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(browser_viewer, "follow_existing_viewer", return_value=0) as follow, \
                redirect_stdout(stdout), redirect_stderr(stderr):
            result = browser_viewer.reuse_existing_viewer(status, 12345)
        if result == 0:
            follow.assert_called_once_with(12345, status["shutdown_token"])
        else:
            follow.assert_not_called()
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
            ("zero_actions_only", 1), ("zero_actions_only", None),
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
        self.assertIn("기존 서버 연결", stdout)
        self.assertIn("http://localhost:12345", stdout)
        self.assertIn("Ctrl+C로 종료", stdout)
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
        self.assertIn("기존 서버 연결", stdout)
        self.assertIn("Ctrl+C로 종료", stdout)
        self.assertEqual(stderr, "")

    def test_other_settings_reuse_the_server_and_point_to_the_browser(self):
        # Settings now switch in the browser, so a healthy server is reused and the
        # terminal says which settings are running instead of refusing (10/7).
        cases = [
            (dict(task="green"), dict(requested_task="red"), "task green"),
            (dict(task="red", mode="pickup", pickup=True, zero_actions_only=False),
             dict(requested_task="red"), "pickup"),
            (dict(task="red", mode="view"), dict(requested_task="red", requested_pickup=True), "view"),
            (dict(task="red", mode="pickup", pickup=True, scenario="sandwich"),
             dict(requested_task="red", requested_mode="pickup"), "sandwich"),
        ]
        for running, requested, mentioned in cases:
            with self.subTest(running=running, requested=requested):
                status = dict(self.status, **running)
                self.assertIsNotNone(self.probe_status(status)[0])
                stdout, stderr = io.StringIO(), io.StringIO()
                with mock.patch.object(browser_viewer, "follow_existing_viewer",
                                       return_value=0) as follow, \
                        redirect_stdout(stdout), redirect_stderr(stderr):
                    result = browser_viewer.reuse_existing_viewer(status, 12345, **requested)
                self.assertEqual(result, 0)
                follow.assert_called_once_with(12345, status["shutdown_token"])
                self.assertIn(mentioned, stdout.getvalue())
                self.assertIn("브라우저", stdout.getvalue())
                self.assertEqual(stderr.getvalue(), "")

    def test_same_settings_reuse_without_a_settings_notice(self):
        status = dict(self.status, task="red", mode="pickup", pickup=True)
        stdout = io.StringIO()
        with mock.patch.object(browser_viewer, "follow_existing_viewer", return_value=0), \
                redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            browser_viewer.reuse_existing_viewer(status, 12345, requested_task="red",
                                                 requested_mode="pickup")
        self.assertNotIn("브라우저", stdout.getvalue())

    def test_pickup_option_requires_a_colour_task(self):
        with self.assertRaises(ValueError):
            browser_viewer.LiveSimulation(task="scene", pickup=True)
        bad_argv = (["--pickup"], ["--mode", "reach"], ["--task", "red", "--scenario", "adjacent"],
                    ["--task", "red", "--pickup", "--mode", "reach"])
        for argv in bad_argv:
            with self.subTest(argv=argv):
                with mock.patch.object(sys, "argv", ["browser_viewer.py"] + argv), \
                        mock.patch.object(browser_viewer, "LiveSimulation") as simulation, \
                        redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    browser_viewer.main()
                simulation.assert_not_called()

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

    def test_legacy_server_without_shutdown_token_is_not_followed(self):
        for token in (None, "", 123, False):
            with self.subTest(token=token):
                result, stdout, stderr = self.reuse(dict(self.status, shutdown_token=token))
                self.assertEqual(result, 1)
                self.assertEqual(stdout, "")
                self.assertIn("이전 버전 서버", stderr)

    def test_shutdown_request_sends_only_the_instance_token(self):
        connection = mock.Mock()
        response = mock.Mock(status=202)
        connection.getresponse.return_value = response
        with mock.patch.object(browser_viewer.http.client, "HTTPConnection",
                               return_value=connection) as constructor:
            self.assertTrue(browser_viewer.request_shutdown(12345, "token", timeout=0.5))
        constructor.assert_called_once_with("127.0.0.1", 12345, timeout=0.5)
        connection.request.assert_called_once_with(
            "POST", "/shutdown", body=b"", headers={"X-RGB-Viewer-Token": "token"})
        response.read.assert_called_once_with(1024)
        connection.close.assert_called_once_with()

    def test_invalid_shutdown_token_never_opens_connection(self):
        for token in (None, "", [], 123, False):
            with self.subTest(token=token):
                with mock.patch.object(browser_viewer.http.client, "HTTPConnection") as connection:
                    self.assertFalse(browser_viewer.request_shutdown(12345, token))
                connection.assert_not_called()

    def test_shutdown_refusal_and_connection_error_are_reported_as_failure(self):
        for code in (200, 403, 404, 500):
            with self.subTest(code=code):
                connection = mock.Mock()
                connection.getresponse.return_value.status = code
                with mock.patch.object(browser_viewer.http.client, "HTTPConnection",
                                       return_value=connection):
                    self.assertFalse(browser_viewer.request_shutdown(12345, "token"))
                connection.close.assert_called_once_with()
        for error in (ConnectionRefusedError(), TimeoutError(),
                      http.client.BadStatusLine("bad status"), ValueError("bad header")):
            with self.subTest(error=type(error).__name__):
                connection = mock.Mock()
                connection.request.side_effect = error
                with mock.patch.object(browser_viewer.http.client, "HTTPConnection",
                                       return_value=connection):
                    self.assertFalse(browser_viewer.request_shutdown(12345, "token"))
                connection.close.assert_called_once_with()

    def test_exit_confirmation_requires_connection_refused_not_network_error(self):
        with mock.patch.object(browser_viewer.time, "monotonic", side_effect=[0, 0]), \
                mock.patch.object(browser_viewer.socket, "create_connection",
                                  side_effect=ConnectionRefusedError()) as connect:
            self.assertTrue(browser_viewer.wait_for_server_exit(12345, timeout=1))
        connect.assert_called_once_with(("127.0.0.1", 12345),
                                        timeout=min(browser_viewer.EXIT_PROBE_TIMEOUT, 1))
        for error in (TimeoutError(), OSError("network error")):
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(browser_viewer.time, "monotonic", side_effect=[0, 0, 1]), \
                        mock.patch.object(browser_viewer.time, "sleep"), \
                        mock.patch.object(browser_viewer.socket, "create_connection", side_effect=error):
                    self.assertFalse(browser_viewer.wait_for_server_exit(12345, timeout=1))

    def test_exit_confirmation_fails_if_listener_stays_open(self):
        with mock.patch.object(browser_viewer.time, "monotonic", side_effect=[0, 0, 1]), \
                mock.patch.object(browser_viewer.time, "sleep"), \
                mock.patch.object(browser_viewer.socket, "create_connection", return_value=mock.MagicMock()):
            self.assertFalse(browser_viewer.wait_for_server_exit(12345, timeout=1))

    def test_windows_exit_probe_has_time_to_observe_connection_refusal(self):
        with mock.patch.object(browser_viewer, "EXIT_PROBE_TIMEOUT", 3.0), \
                mock.patch.object(browser_viewer.time, "monotonic", side_effect=[0, 0]), \
                mock.patch.object(browser_viewer.socket, "create_connection",
                                  side_effect=ConnectionRefusedError()) as connect:
            self.assertTrue(browser_viewer.wait_for_server_exit(12345, timeout=15))
        connect.assert_called_once_with(("127.0.0.1", 12345), timeout=3.0)

    def test_exit_probe_timeout_is_limited_to_the_remaining_deadline(self):
        with mock.patch.object(browser_viewer, "EXIT_PROBE_TIMEOUT", 3.0), \
                mock.patch.object(browser_viewer.time, "monotonic", side_effect=[0, 0.75, 1]), \
                mock.patch.object(browser_viewer.time, "sleep") as sleep, \
                mock.patch.object(browser_viewer.socket, "create_connection",
                                  side_effect=TimeoutError()) as connect:
            self.assertFalse(browser_viewer.wait_for_server_exit(12345, timeout=1))
        connect.assert_called_once_with(("127.0.0.1", 12345), timeout=0.25)
        sleep.assert_not_called()

    def test_stop_existing_viewer_requires_identity_and_actual_exit(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(browser_viewer, "probe_existing_viewer", return_value=self.status) as probe, \
                mock.patch.object(browser_viewer, "request_shutdown", return_value=True) as shutdown, \
                mock.patch.object(browser_viewer, "wait_for_server_exit", return_value=True) as wait, \
                redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(browser_viewer.stop_existing_viewer(12345), 0)
        probe.assert_called_once_with(12345)
        shutdown.assert_called_once_with(12345, self.status["shutdown_token"])
        wait.assert_called_once_with(12345)
        self.assertIn("서버 종료", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_stop_unknown_service_does_not_send_shutdown(self):
        for is_closed, expected in ((True, 0), (False, 1)):
            with self.subTest(is_closed=is_closed):
                stdout, stderr = io.StringIO(), io.StringIO()
                with mock.patch.object(browser_viewer, "probe_existing_viewer", return_value=None), \
                        mock.patch.object(browser_viewer, "request_shutdown") as shutdown, \
                        mock.patch.object(browser_viewer, "wait_for_server_exit", return_value=is_closed) as wait, \
                        redirect_stdout(stdout), redirect_stderr(stderr):
                    self.assertEqual(browser_viewer.stop_existing_viewer(12345), expected)
                shutdown.assert_not_called()
                wait.assert_called_once_with(12345, timeout=browser_viewer.EXIT_PROBE_TIMEOUT)
                if is_closed:
                    self.assertIn("종료되어 있습니다", stdout.getvalue())
                else:
                    self.assertIn("종료하지 않았습니다", stderr.getvalue())

    def test_stop_failure_is_not_announced_as_success(self):
        for accepted, exited in ((False, False), (True, False)):
            with self.subTest(accepted=accepted, exited=exited):
                stdout, stderr = io.StringIO(), io.StringIO()
                with mock.patch.object(browser_viewer, "request_shutdown", return_value=accepted), \
                        mock.patch.object(browser_viewer, "wait_for_server_exit", return_value=exited) as wait, \
                        redirect_stdout(stdout), redirect_stderr(stderr):
                    self.assertEqual(browser_viewer.stop_existing_viewer(12345, self.status), 1)
                self.assertEqual(stdout.getvalue(), "")
                self.assertTrue(stderr.getvalue())
                if accepted:
                    wait.assert_called_once_with(12345)
                else:
                    wait.assert_not_called()

    def test_follow_existing_viewer_ctrl_c_stops_that_instance(self):
        for result in (0, 1):
            with self.subTest(result=result):
                with mock.patch.object(browser_viewer.time, "sleep", side_effect=[None, KeyboardInterrupt]), \
                        mock.patch.object(browser_viewer, "probe_existing_viewer", return_value=self.status) as probe, \
                        mock.patch.object(browser_viewer, "stop_existing_viewer", return_value=result) as stop:
                    self.assertEqual(browser_viewer.follow_existing_viewer(
                        12345, self.status["shutdown_token"]), result)
                probe.assert_called_once_with(12345)
                stop.assert_called_once_with(12345, status={"shutdown_token": self.status["shutdown_token"]})

    def test_follow_ended_or_replaced_server_never_stops_replacement(self):
        for current in (None, dict(self.status, shutdown_token="replacement-token")):
            with self.subTest(current=current is not None):
                with mock.patch.object(browser_viewer.time, "sleep"), \
                        mock.patch.object(browser_viewer, "probe_existing_viewer", return_value=current), \
                        mock.patch.object(browser_viewer, "wait_for_server_exit", return_value=True) as wait, \
                        mock.patch.object(browser_viewer, "stop_existing_viewer") as stop:
                    self.assertEqual(browser_viewer.follow_existing_viewer(
                        12345, self.status["shutdown_token"]), 0)
                stop.assert_not_called()
                if current is None:
                    wait.assert_called_once_with(12345, timeout=browser_viewer.EXIT_PROBE_TIMEOUT)
                else:
                    wait.assert_not_called()

    def test_transient_status_failure_keeps_foreground_ctrl_c_available(self):
        with mock.patch.object(browser_viewer.time, "sleep", side_effect=[None, None, KeyboardInterrupt]), \
                mock.patch.object(browser_viewer, "probe_existing_viewer", side_effect=[None, self.status]) as probe, \
                mock.patch.object(browser_viewer, "wait_for_server_exit", return_value=False) as wait, \
                mock.patch.object(browser_viewer, "stop_existing_viewer", return_value=0) as stop:
            self.assertEqual(browser_viewer.follow_existing_viewer(
                12345, self.status["shutdown_token"]), 0)
        self.assertEqual(probe.call_args_list, [mock.call(12345), mock.call(12345)])
        wait.assert_called_once_with(12345, timeout=browser_viewer.EXIT_PROBE_TIMEOUT)
        stop.assert_called_once_with(12345, status={"shutdown_token": self.status["shutdown_token"]})

    def test_main_stop_option_never_creates_simulation_or_server(self):
        for result in (0, 1):
            with self.subTest(result=result):
                with mock.patch.object(sys, "argv", ["browser_viewer.py", "--port", "12345", "--stop"]), \
                        mock.patch.object(browser_viewer, "LiveSimulation") as simulation, \
                        mock.patch.object(browser_viewer, "make_server") as server, \
                        mock.patch.object(browser_viewer, "stop_existing_viewer", return_value=result) as stop:
                    self.assertEqual(browser_viewer.main(), result)
                stop.assert_called_once_with(12345)
                simulation.assert_not_called()
                server.assert_not_called()

    def test_main_ctrl_c_closes_owned_simulation_and_server(self):
        server = mock.Mock()
        server.serve_forever.side_effect = KeyboardInterrupt
        simulation = mock.Mock()
        with mock.patch.object(sys, "argv", ["browser_viewer.py"]), \
                mock.patch.object(browser_viewer, "LiveSimulation", return_value=simulation), \
                mock.patch.object(browser_viewer, "make_server", return_value=server), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(browser_viewer.main(), 0)
        simulation.start.assert_called_once_with()
        simulation.stop.assert_called_once_with()
        server.server_close.assert_called_once_with()


class PlaybackControlTests(unittest.TestCase):
    """The --pickup frame buffer and controls, without a simulator."""

    def setUp(self):
        self.sim = browser_viewer.LiveSimulation(task="red", pickup=True, seed=4)

    def add(self, count):
        with self.sim.condition:
            for _ in range(count):
                n = len(self.sim.frames)
                self.sim._append_frame(b"frame%d" % n, n, "approach", False)

    def test_new_frames_follow_until_the_viewer_steps_back(self):
        self.add(3)
        self.assertEqual((self.sim.cursor, self.sim.jpeg), (2, b"frame2"))
        self.sim.control({"action": "step", "delta": -1})
        self.assertTrue(self.sim.paused)
        self.add(2)
        self.assertEqual((self.sim.cursor, self.sim.jpeg), (1, b"frame1"))
        self.assertEqual(self.sim.status["frames"], 5)

    def test_seek_first_last_and_bounds(self):
        self.add(5)
        self.sim.control({"action": "seek", "index": 2})
        self.assertEqual(self.sim.status["step"], 2)
        self.sim.control({"action": "seek", "index": 99})
        self.assertEqual(self.sim.cursor, 4)
        self.sim.control({"action": "first"})
        self.assertEqual(self.sim.cursor, 0)
        self.sim.control({"action": "step", "delta": -1})
        self.assertEqual(self.sim.cursor, 0)
        self.sim.control({"action": "last"})
        self.assertEqual(self.sim.cursor, 4)
        for bad in ({"action": "seek", "index": True}, {"action": "seek", "index": "1"},
                    {"action": "step", "delta": 2}, {"action": "step", "delta": False}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.sim.control(bad)

    def test_step_forward_at_newest_frame_asks_for_one_simulation_step(self):
        self.add(2)
        self.sim.control({"action": "step", "delta": 1})
        self.assertTrue(self.sim.step_once)
        self.sim.step_once = False
        self.sim.episode_done = True
        self.sim.control({"action": "step", "delta": 1})
        self.assertFalse(self.sim.step_once)

    def test_seed_requests_and_auto(self):
        self.sim.control({"action": "run_seed", "seed": 17})
        self.assertEqual(self.sim.request,
                         {"task": "red", "mode": "pickup", "scenario": "none", "seed": 17})
        self.sim.control({"action": "next"})
        self.assertEqual(self.sim.request["seed"], 5)
        for bad in (-1, 2 ** 31, 1.5, True, "3"):
            with self.subTest(seed=bad):
                with self.assertRaises(ValueError):
                    self.sim.control({"action": "run_seed", "seed": bad})
        self.sim.control({"action": "auto", "on": True})
        self.assertTrue(self.sim.status["auto_advance"])
        with self.assertRaises(ValueError):
            self.sim.control({"action": "auto", "on": 1})
        with self.assertRaises(ValueError):
            self.sim.control({"action": "rewind-time"})

    def test_display_changes_wake_the_stream(self):
        self.add(3)
        jpeg, version = self.sim.wait_for_frame(-1, timeout=0)
        self.assertEqual(jpeg, b"frame2")
        self.assertIsNone(self.sim.wait_for_frame(version, timeout=0))
        self.sim.control({"action": "seek", "index": 0})
        self.assertEqual(self.sim.wait_for_frame(version, timeout=0)[0], b"frame0")

    def test_controls_work_in_every_mode(self):
        for task, mode in (("scene", "view"), ("red", "view"), ("blue", "reach")):
            with self.subTest(task=task, mode=mode):
                sim = browser_viewer.LiveSimulation(task=task, mode=mode)
                self.assertTrue(sim.control({"action": "pause"})["paused"])
                self.assertEqual(sim.status["zero_actions_only"], mode == "view")

    def test_load_validates_the_whole_configuration(self):
        self.sim.control({"action": "load", "task": "blue", "mode": "reach",
                          "scenario": "none", "seed": 9})
        self.assertEqual(self.sim.request,
                         {"task": "blue", "mode": "reach", "scenario": "none", "seed": 9})
        bad = [
            {"task": "purple", "mode": "view", "scenario": "none", "seed": 0},
            {"task": "scene", "mode": "pickup", "scenario": "none", "seed": 0},
            {"task": "red", "mode": "reach", "scenario": "adjacent", "seed": 0},
            {"task": "red", "mode": "pickup", "scenario": "upside-down", "seed": 0},
            {"task": "red", "mode": "fly", "scenario": "none", "seed": 0},
            {"task": "red", "mode": "view", "scenario": "none", "seed": -3},
            {"task": "red", "mode": "view", "scenario": "none"},
        ]
        for config in bad:
            with self.subTest(config=config):
                with self.assertRaises(ValueError):
                    self.sim.control(dict(config, action="load"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
