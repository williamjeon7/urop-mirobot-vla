"""Exercise Windows bridge RPCs over HTTP without connected USB hardware."""
from contextlib import contextmanager
from argparse import Namespace
from http.server import ThreadingHTTPServer
import json
import threading
import time
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from robot.policy_bridge import D405Camera, PolicyBridge, RobotIO, make_handler
from server.policy_client import PolicyClient
from tests.test_policy_bridge import FakeSerial


@contextmanager
def remote_fixture(root, execute=True):
    camera = D405Camera(video_dir=root / "windows")
    camera.error = ""
    robot = RobotIO(FakeSerial(), execute=execute)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(PolicyBridge(robot, camera), token="test"))
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    thread.start()
    try:
        yield PolicyClient(f"http://127.0.0.1:{server.server_port}", token="test"), robot, camera
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        camera.close()


def test_prepare_requires_execute_and_does_not_move_read_only_robot(tmp_path):
    with remote_fixture(tmp_path, execute=False) as (client, robot, _):
        with pytest.raises(RuntimeError, match="read-only"):
            client.prepare()
        assert robot.ser.commands == []


def test_recording_names_reports_existing_windows_run_directories(tmp_path):
    windows = tmp_path / "windows"
    (windows / "I2").mkdir(parents=True)
    (windows / "I5").mkdir()
    (windows / "notes").mkdir()
    with remote_fixture(tmp_path) as (client, _, _):
        assert client.recording_names() == ["I2", "I5"]


def test_prepare_homes_opens_verifies_and_deduplicates_requests(tmp_path):
    with remote_fixture(tmp_path) as (client, robot, _), patch("robot.policy_setup.time.sleep"):
        result = client._request("/prepare", {"request_id": "same"})
        assert result["prepared"]
        assert result["cart6"] == [198.67, 0., 230.72, 0., 0., 0.]
        commands = robot.ser.commands.copy()
        assert "$H" in commands and "M4 S40" in commands
        client._request("/prepare", {"request_id": "same"})
        assert robot.ser.commands == commands


def test_remote_video_download_repeats_runs_and_never_sends_robot_commands(tmp_path):
    image = np.full((480, 640, 3), (10, 20, 220), dtype=np.uint8)
    with remote_fixture(tmp_path) as (client, robot, camera):
        for name in ("I1", "I2"):
            directory = tmp_path / "server" / name
            directory.mkdir(parents=True)
            client.start_recording(name)
            for i in range(12):
                camera.video.write(image, time.monotonic(), i, i*1000/30)
            assert client.stop_recording()["frames"] == 12
            paths = client.download_recording(name, directory)
            cap = cv2.VideoCapture(paths["video"])
            try:
                assert cap.isOpened() and int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 12
                ok, frame = cap.read()
                assert ok and frame.shape == (480, 640, 3)
            finally:
                cap.release()
            assert json.loads((directory / (name + "_video.json")).read_text())["frames"] == 12
            with pytest.raises(FileExistsError):
                client.download_recording(name, directory)
            assert (directory / (name + ".mp4")).stat().st_size > 0
        assert robot.ser.commands == []


def test_remote_recording_rejects_path_traversal(tmp_path):
    with remote_fixture(tmp_path) as (client, _, camera):
        with pytest.raises(RuntimeError, match="name must"):
            client.start_recording("../../outside")
        assert not (tmp_path / "windows").exists()


def test_remote_run_rejects_concurrent_initialization(tmp_path):
    import fcntl
    from tools import run_mirobot_local as local
    from tools import run_mirobot_remote as remote
    (tmp_path / "logs").mkdir()
    with (tmp_path / "logs/mirobot_remote.lock").open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with patch.object(local, "REPO", tmp_path), patch.object(remote, "_run") as execute:
            with pytest.raises(RuntimeError, match="다른 원격 로봇 실행"):
                remote.run(Namespace(devices=False, check=False), [])
            execute.assert_not_called()
