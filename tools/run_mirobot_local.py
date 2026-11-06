"""Run USB bridge and inference together so local deployment needs no SSH.

The default is a four-command preview without movement. With --execute, home,
open the gripper, and verify the initial pose before starting the model.
Video starts with the first inference. Children stop when inference ends or the
launcher is interrupted.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
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
from robot.policy_setup import prepare_with_probe
from tools.probe_mirobot import Probe, fields, find_field, is_error, is_ok, state_of
from tools.run_gcode import parse_file, pose_of

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO / "Mirobot_data/W10"


def reserve_inference(root, reserved_names=()):
    """Atomically reserve I1, I2, ... without overwriting a previous run."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    numbers = [int(match.group(1)) for path in root.iterdir()
               if (match := re.fullmatch(r"I([1-9][0-9]*)", path.name))]
    numbers.extend(int(match.group(1)) for name in reserved_names
                   if isinstance(name, str) and (match := re.fullmatch(r"I([1-9][0-9]*)", name)))
    number = max(numbers, default=0) + 1
    while True:
        directory = root / f"I{number}"
        try:
            directory.mkdir()
            return directory
        except FileExistsError:
            number += 1


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



def prepare_robot(port, directory):
    import serial
    print("호밍 → 그리퍼 열기(S40) → 초기 위치 이동을 시작합니다.", flush=True)
    with serial.Serial(port, 115200, timeout=.05, write_timeout=1) as ser:
        probe = Probe(ser, directory / "initialization.jsonl")
        try:
            time.sleep(2)
            prepare_with_probe(probe)
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
            directory = reserve_inference(args.output_root)
            video_path = directory / f"{directory.name}.mp4"
            policy.extend(("--log-dir", str(directory / "policy")))
            if not args.no_record_video:
                policy.append("--record-video")
                print(f"실행 기록: {directory}\n영상: {video_path} (첫 추론부터 자동 녹화)", flush=True)
            else:
                print(f"실행 기록: {directory} (영상 저장 안 함)", flush=True)
            if args.execute:
                prepare_robot(port, directory)
            command = [sys.executable, "-m", "robot.policy_bridge", "--serial-port", port,
                       "--listen-host", "127.0.0.1", "--http-port", str(args.http_port)]
            if not args.no_record_video:
                command.extend(("--video-out", str(video_path)))
            if args.execute:
                command.append("--execute")
                policy.append("--execute")
            bridge = subprocess.Popen(command, cwd=REPO, env=env, start_new_session=True)
            wait_for_bridge(bridge, url, env.get("MIROBOT_POLICY_TOKEN"))
            policy.extend(("--bridge-url", url))
        inference = subprocess.Popen(policy, cwd=REPO, env=env, start_new_session=True)
        return inference.wait()
    finally:
        stop_child(inference)
        stop_child(bridge)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
        epilog="모델 옵션은 그대로 전달됩니다. 예: --color red --max-steps 4; --bridge-check")
    parser.add_argument("--serial-port", default=os.environ.get("MIROBOT_SERIAL_PORT"),
                        help="로봇 포트 (예: /dev/ttyUSB0). 생략하면 USB 시리얼 포트 1개를 자동 선택")
    parser.add_argument("--http-port", type=int, default=8891)
    parser.add_argument("--no-record-video", action="store_true", help="Do not save an MP4 recording")
    parser.add_argument("--remote", action="store_true", help="Windows USB 브리지를 SSH 터널로 사용")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT,
                        help="I1, I2, ... 실행 기록의 상위 폴더 (기본: Mirobot_data/W10)")
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
