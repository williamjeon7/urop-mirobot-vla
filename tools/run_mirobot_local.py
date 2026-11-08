"""Run USB bridge and inference together so local deployment needs no SSH.

The default is a four-command preview without movement. With --execute, home,
open the gripper, and verify the initial pose before starting the model.
Video starts with the first inference. Children stop when inference ends or the
launcher is interrupted.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from docs.W9.d405.devices import inspect_devices
from robot.policy_bridge import DEFAULT_COLOR_PROFILE, PROTOCOL
from common.gcode import HOME_SEQUENCE
from common.recording_names import COLORS
from common.trial_numbers import compact_all, discard_if_never_started, reserve as reserve_trial
from robot.policy_setup import prepare_with_probe
from tools.probe_mirobot import Probe, fields, find_field, is_error, is_ok, state_of
from tools.run_gcode import parse_file, pose_of
from server.experiment_log import capture_trial_layout, finish_launch, start_launch

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO / "Mirobot_data/W10"


def policy_color(policy_args):
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--color", choices=COLORS, default="red")
    return parser.parse_known_args(policy_args)[0].color


def should_save(args):
    """Only real runs become numbered trials; a preview moves nothing, so it saves nothing unless --save."""
    if getattr(args, "no_save", False):
        return False
    return bool(getattr(args, "execute", False) or getattr(args, "save", False))


def reserve_inference(root, color=None):
    """Reserve I{N+1}{color} after renumbering that colour's folders to 1..N (deleted numbers are reused)."""
    if color is not None and color not in COLORS:
        raise ValueError("Unknown trial color")
    return reserve_trial(root, color)


def select_robot_port(report, requested=None):
    ports = [row["device"] for row in report["robot_serial_ports"]]
    if requested:
        if requested not in ports and os.path.realpath(requested) not in ports:
            raise RuntimeError(f"로봇 포트가 없습니다: {requested}; 감지된 포트: {ports}")
        return requested
    if len(ports) != 1:
        raise RuntimeError(
            f"로봇 USB 시리얼 포트가 {len(ports)}개 감지되었습니다: {ports}. "
            "Mirobot을 OASYS에 USB로 연결하고, 여러 개이면 --serial-port /dev/ttyUSB0 을 지정하세요."
        )
    return ports[0]


def check_devices(report, requested=None):
    if report["errors"]:
        raise RuntimeError("; ".join(report["errors"]))
    port = select_robot_port(report, requested)
    serial = json.loads(DEFAULT_COLOR_PROFILE.read_text())["camera_serial"]
    if not any(row.get("serial_number") == serial for row in report["realsense_cameras"]):
        raise RuntimeError(f"D405 {serial}이 감지되지 않습니다. 카메라를 OASYS에 USB로 연결하세요.")
    if not os.access(port, os.R_OK | os.W_OK):
        raise RuntimeError(
            f"{port} 읽기·쓰기 권한이 없습니다. 관리자가 이 계정의 시리얼/USB 접근 권한을 설정해야 합니다."
        )
    return port



def prepare_robot(port, directory, home=False):
    import serial
    print(("호밍 → " if home else "") + "그리퍼 열기(S40) → 초기 위치 이동을 시작합니다.", flush=True)
    with serial.Serial(port, 115200, timeout=.05, write_timeout=1) as ser:
        if directory is None:
            probe = Probe.__new__(Probe)
            probe.ser, probe.log_file = ser, io.StringIO()
        else:
            probe = Probe(ser, directory / "initialization.jsonl")
        try:
            time.sleep(2)
            prepare_with_probe(probe, home=home)
        finally:
            probe.log_file.close()


def stop_child(process):
    if process is None or process.poll() is not None:
        return
    for sig, timeout in ((signal.SIGINT, 5), (signal.SIGTERM, 3), (signal.SIGKILL, 3)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            pass


def wait_for_bridge(process, url, token=None, timeout=30):
    # Loopback must remain local even when the shell has HTTP proxy settings.
    opener = build_opener(ProxyHandler({}))
    headers = {"Authorization": "Bearer " + token} if token else {}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"브리지가 시작 중 종료되었습니다 (exit {process.returncode}). 위 로그를 확인하세요.")
        try:
            with opener.open(Request(url + "/health", headers=headers), timeout=.5) as response:
                health = json.load(response)
            if health.get("ok") is True and health.get("protocol") == PROTOCOL:
                return
        except (URLError, OSError, ValueError):
            pass
        time.sleep(.1)
    raise RuntimeError("브리지 시작 시간 초과. 카메라/로봇 연결 및 장치 권한을 확인하세요.")


def run(args, policy_args):
    if any(arg == "--bridge-url" or arg.startswith("--bridge-url=") for arg in policy_args):
        raise ValueError("로컬 실행의 브리지 주소는 자동으로 설정됩니다. --http-port 를 사용하세요.")
    if getattr(args, "remote", False) and not args.offline_smoke:
        from tools.run_mirobot_remote import run as run_remote
        return run_remote(args, policy_args)
    policy = ["bash", str(REPO / "tools/run_mirobot_policy.sh"), *policy_args]
    bridge = inference = None
    directory = launch = None
    code = None
    save = should_save(args)
    env = os.environ.copy()
    for key in ("NO_PROXY", "no_proxy"):
        env[key] = ",".join(filter(None, (env.get(key), "127.0.0.1", "localhost")))
    try:
        if args.offline_smoke:
            policy.append("--offline-smoke")
        else:
            report = inspect_devices()
            if report.get("robot_serial_ports") == [] and report.get("realsense_cameras") == []:
                from tools.run_mirobot_remote import run as run_remote
                return run_remote(args, policy_args)
            if args.devices:
                print(json.dumps(report, indent=2, ensure_ascii=False))
                return int(bool(report["errors"]))
            port = check_devices(report, args.serial_port)
            print(f"USB 장치 확인 완료: {port}, 학습에 사용한 D405", flush=True)
            if args.check:
                return 0
            url = f"http://127.0.0.1:{args.http_port}"
            # Never attach to, stop, or enable an already running bridge.
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", args.http_port))
            if save:
                directory = reserve_inference(args.output_root, color=policy_color(policy_args))
                launch = start_launch(directory, policy_args, "execute" if args.execute else "preview")
                policy_args = capture_trial_layout(directory, policy_args, args.execute)
                policy = ["bash", str(REPO / "tools/run_mirobot_policy.sh"), *policy_args,
                          "--log-dir", str(directory / "policy")]
            else:
                policy.append("--no-save")
                print("이번 확인 실행은 영상과 실험 파일을 저장하지 않습니다.", flush=True)
            video_path = directory / f"{directory.name}.mp4" if directory else None
            if save and not args.no_record_video:
                policy.append("--record-video")
                print(f"실행 기록: {directory}\n영상: {video_path} (첫 추론부터 자동 녹화)", flush=True)
            elif save:
                print(f"실행 기록: {directory} (영상 저장 안 함)", flush=True)
            if args.execute:
                prepare_robot(port, directory)
            command = [sys.executable, "-m", "robot.policy_bridge", "--serial-port", port,
                       "--listen-host", "127.0.0.1", "--http-port", str(args.http_port)]
            if save and not args.no_record_video:
                command.extend(("--video-out", str(video_path)))
            if args.execute:
                command.append("--execute")
                policy.append("--execute")
            bridge = subprocess.Popen(command, cwd=REPO, env=env, start_new_session=True)
            wait_for_bridge(bridge, url, env.get("MIROBOT_POLICY_TOKEN"))
            policy.extend(("--bridge-url", url))
        inference = subprocess.Popen(policy, cwd=REPO, env=env, start_new_session=True)
        code = inference.wait()
        return code
    finally:
        stop_child(inference)
        stop_child(bridge)
        if directory is not None and launch is not None:
            finish_launch(directory, launch, code=code,
                          error=sys.exc_info()[1])
            discard_if_never_started(directory, launch)
            compact_all(args.output_root, COLORS)  # reflect folders deleted during the run


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
        epilog="모델 옵션은 그대로 전달됩니다. 예: --color red --max-steps 4; --bridge-check")
    parser.add_argument("--serial-port", default=os.environ.get("MIROBOT_SERIAL_PORT"),
                        help="로봇 포트 (예: /dev/ttyUSB0). 생략하면 USB 시리얼 포트 1개를 자동 선택")
    parser.add_argument("--http-port", type=int, default=8891)
    parser.add_argument("--no-record-video", action="store_true", help="Do not save an MP4 recording")
    parser.add_argument("--no-save", action="store_true", help="확인용: 영상·실험 파일·시행 번호를 저장하지 않음")
    parser.add_argument("--no-return", action="store_true",
                        help="실제 실행(--execute)이 끝난 뒤 초기 위치로 돌아가지 않음 (기본: 위로 올린 뒤 초기 위치로 복귀)")
    parser.add_argument("--save", action="store_true", help="미리보기도 시행 폴더로 저장 (기본: --execute 일 때만 저장)")
    parser.add_argument("--remote", action="store_true", help="Windows USB 브리지를 SSH 터널로 사용")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT,
                        help="I1red, I1blue, I1green, ... 실행 기록의 상위 폴더 (기본: Mirobot_data/W10)")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--devices", action="store_true", help="USB 장치 목록만 표시")
    modes.add_argument("--check", action="store_true", help="선택한 USB 장치와 시리얼 접근 권한 확인")
    modes.add_argument("--offline-smoke", action="store_true", help="USB 없이 저장 관측으로 모델 확인")
    modes.add_argument("--execute", action="store_true", help="호밍·그리퍼 열기·초기 위치 준비 후 실제 실행")
    args, policy_args = parser.parse_known_args()
    if not 1 <= args.http_port <= 65535:
        parser.error("--http-port 는 1–65535여야 합니다.")
    try:
        code = run(args, policy_args)
    except KeyboardInterrupt:
        parser.exit(130, "중단했습니다. 로컬 브리지와 모델 프로세스를 종료했습니다.\n")
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"실행 중단: {error}\n")
    parser.exit(code if code >= 0 else 128 - code)


if __name__ == "__main__":
    main()
