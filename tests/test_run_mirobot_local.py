"""Check device selection and child cleanup without accessing robot hardware."""
from argparse import Namespace
from contextlib import ExitStack
from unittest.mock import Mock, patch

import pytest

from tools import run_mirobot_local as local


def args(**overrides):
    values = dict(serial_port=None, http_port=8891, devices=False, check=False,
                  offline_smoke=False, execute=False, no_record_video=False, output_root=None)
    return Namespace(**(values | overrides))


def test_ambiguous_serial_ports_require_explicit_selection():
    report = {"robot_serial_ports": [{"device": "/dev/ttyUSB0"}, {"device": "/dev/ttyUSB1"}]}
    with pytest.raises(RuntimeError, match="--serial-port"):
        local.select_robot_port(report)
    assert local.select_robot_port(report, "/dev/ttyUSB1") == "/dev/ttyUSB1"
    with pytest.raises(RuntimeError, match="감지된 포트"):
        local.select_robot_port(report, "/dev/ttyUSB2")


def test_missing_camera_blocks_startup():
    report = {"robot_serial_ports": [{"device": "/dev/ttyUSB0"}],
              "realsense_cameras": [], "errors": []}
    with pytest.raises(RuntimeError, match="D405"):
        local.check_devices(report)


@pytest.mark.parametrize("execute", [False, True])
def test_local_launch_arms_both_processes_only_when_requested_and_cleans_bridge(execute, tmp_path):
    bridge, inference = Mock(), Mock()
    bridge.poll.return_value = None
    bridge.wait.return_value = 0
    inference.poll.return_value = 0
    inference.wait.return_value = 0
    with ExitStack() as stack:
        stack.enter_context(patch.object(local, "inspect_devices", return_value={}))
        stack.enter_context(patch.object(local, "check_devices", return_value="/dev/ttyUSB0"))
        stack.enter_context(patch.object(local.socket, "socket"))
        ready = stack.enter_context(patch.object(local, "wait_for_bridge"))
        spawn = stack.enter_context(patch.object(local.subprocess, "Popen", side_effect=[bridge, inference]))
        signal_group = stack.enter_context(patch.object(local.os, "killpg"))
        prepare = stack.enter_context(patch.object(local, "prepare_robot"))
        assert local.run(args(execute=execute, output_root=tmp_path), ["--color", "red"]) == 0
    bridge_command, policy_command = [call.args[0] for call in spawn.call_args_list]
    assert ("--execute" in bridge_command) is execute
    assert ("--execute" in policy_command) is execute
    assert bridge_command[bridge_command.index("--listen-host") + 1] == "127.0.0.1"
    assert policy_command[policy_command.index("--bridge-url") + 1] == "http://127.0.0.1:8891"
    assert all(call.kwargs["start_new_session"] for call in spawn.call_args_list)
    assert "--record-video" in policy_command
    assert bridge_command[bridge_command.index("--video-out") + 1] == str(tmp_path / "I1/I1.mp4")
    assert policy_command[policy_command.index("--log-dir") + 1] == str(tmp_path / "I1/policy")
    assert prepare.call_count == int(execute)
    ready.assert_called_once()
    signal_group.assert_called_once_with(bridge.pid, local.signal.SIGINT)


def test_until_pickup_without_video_is_forwarded_without_step_limit(tmp_path):
    bridge, inference = Mock(), Mock()
    bridge.poll.return_value = None
    bridge.wait.return_value = 0
    inference.poll.return_value = 0
    inference.wait.return_value = 0
    with ExitStack() as stack:
        stack.enter_context(patch.object(local, "inspect_devices", return_value={}))
        stack.enter_context(patch.object(local, "check_devices", return_value="/dev/ttyUSB0"))
        stack.enter_context(patch.object(local.socket, "socket"))
        stack.enter_context(patch.object(local, "wait_for_bridge"))
        spawn = stack.enter_context(patch.object(local.subprocess, "Popen", side_effect=[bridge, inference]))
        stack.enter_context(patch.object(local.os, "killpg"))
        stack.enter_context(patch.object(local, "prepare_robot"))
        assert local.run(args(execute=True, no_record_video=True, output_root=tmp_path),
                         ["--color", "red", "--execute", "--until-pickup", "--open-loop-steps", "1"]) == 0
    bridge_command, policy_command = [call.args[0] for call in spawn.call_args_list]
    assert "--video-out" not in bridge_command
    assert "--record-video" not in policy_command
    assert "--until-pickup" in policy_command
    assert "--max-steps" not in policy_command


def test_failed_bridge_is_cleaned_and_model_never_starts(tmp_path):
    bridge = Mock()
    bridge.poll.return_value = None
    with ExitStack() as stack:
        stack.enter_context(patch.object(local, "inspect_devices", return_value={}))
        stack.enter_context(patch.object(local, "check_devices", return_value="/dev/ttyUSB0"))
        stack.enter_context(patch.object(local.socket, "socket"))
        stack.enter_context(patch.object(local, "wait_for_bridge", side_effect=RuntimeError("camera failed")))
        spawn = stack.enter_context(patch.object(local.subprocess, "Popen", return_value=bridge))
        signal_group = stack.enter_context(patch.object(local.os, "killpg"))
        with pytest.raises(RuntimeError, match="camera failed"):
            local.run(args(output_root=tmp_path), [])
    spawn.assert_called_once()
    signal_group.assert_called_once_with(bridge.pid, local.signal.SIGINT)


def test_offline_run_needs_no_usb_and_preserves_model_failure_status():
    inference = Mock()
    inference.wait.return_value = 17
    inference.poll.return_value = 17
    with patch.object(local, "inspect_devices") as inspect, \
         patch.object(local.subprocess, "Popen", return_value=inference) as spawn:
        assert local.run(args(offline_smoke=True), ["--max-steps", "2"]) == 17
    inspect.assert_not_called()
    command = spawn.call_args.args[0]
    assert "--offline-smoke" in command
    assert "--bridge-url" not in command


def test_interrupt_stops_model_and_bridge(tmp_path):
    bridge, inference = Mock(), Mock()
    bridge.poll.return_value = inference.poll.return_value = None
    inference.wait.side_effect = [KeyboardInterrupt, 130]
    with ExitStack() as stack:
        stack.enter_context(patch.object(local, "inspect_devices", return_value={}))
        stack.enter_context(patch.object(local, "check_devices", return_value="/dev/ttyUSB0"))
        stack.enter_context(patch.object(local.socket, "socket"))
        stack.enter_context(patch.object(local, "wait_for_bridge"))
        stack.enter_context(patch.object(local.subprocess, "Popen", side_effect=[bridge, inference]))
        signal_group = stack.enter_context(patch.object(local.os, "killpg"))
        with pytest.raises(KeyboardInterrupt):
            local.run(args(output_root=tmp_path), [])
    assert [call.args[0] for call in signal_group.call_args_list] == [inference.pid, bridge.pid]


def test_numbered_runs_never_replace_previous_records(tmp_path):
    first = local.reserve_inference(tmp_path)
    assert first.name == "I1"
    (first / "keep.txt").write_text("original")
    (tmp_path / "I3").mkdir()
    assert local.reserve_inference(tmp_path).name == "I4"
    assert (first / "keep.txt").read_text() == "original"


def test_numbered_runs_skip_ids_reserved_by_windows(tmp_path):
    (tmp_path / "I1").mkdir()
    assert local.reserve_inference(tmp_path, ["I3", "I7", "not-an-id"]).name == "I8"


def test_initialization_homes_opens_gripper_and_verifies_pose():
    probe = Mock()
    probe.send.return_value = ([(0, "ok")], .01)
    status = "<Idle,Cartesian coordinate(XYZ RxRyRz):198.67,0,230.72,0,0,0>"
    probe.wait_settled.return_value = (status, .2)
    with patch.object(local.time, "sleep"):
        local.prepare_with_probe(probe)
    commands = [call.args[0] for call in probe.send.call_args_list]
    assert commands[:4] == list(local.HOME_SEQUENCE)
    assert commands.index("M4 S40") < next(i for i, cmd in enumerate(commands) if cmd.startswith("G0 "))
    assert probe.wait_settled.call_count == 2


def test_failed_initialization_blocks_bridge_and_inference(tmp_path):
    with ExitStack() as stack:
        stack.enter_context(patch.object(local, "inspect_devices", return_value={}))
        stack.enter_context(patch.object(local, "check_devices", return_value="/dev/ttyUSB0"))
        stack.enter_context(patch.object(local.socket, "socket"))
        stack.enter_context(patch.object(local, "prepare_robot", side_effect=RuntimeError("homing failed")))
        spawn = stack.enter_context(patch.object(local.subprocess, "Popen"))
        with pytest.raises(RuntimeError, match="homing failed"):
            local.run(args(execute=True, output_root=tmp_path), [])
    spawn.assert_not_called()


@pytest.mark.parametrize("reported,elapsed", [
    ("<Idle,Cartesian coordinate(XYZ RxRyRz):100,0,100,0,0,0>", .2),
    ("<Run,Cartesian coordinate(XYZ RxRyRz):198.67,0,230.72,0,0,0>", None),
])
def test_initialization_rejects_unreached_or_moving_robot(reported, elapsed):
    probe = Mock()
    probe.send.return_value = ([(0, "ok")], .01)
    probe.wait_settled.side_effect = [
        ("<Idle,Cartesian coordinate(XYZ RxRyRz):200,0,250,0,0,0>", .2),
        (reported, elapsed),
    ]
    with patch.object(local.time, "sleep"), pytest.raises(RuntimeError):
        local.prepare_with_probe(probe)
