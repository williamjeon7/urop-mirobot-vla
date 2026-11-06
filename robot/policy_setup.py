"""Shared verified homing and start-pose preparation for local and remote USB."""
import math
from pathlib import Path
import time

from common.gcode import HOME_SEQUENCE
from tools.probe_mirobot import fields, find_field, is_error, is_ok, state_of
from tools.run_gcode import parse_file, pose_of

REPO = Path(__file__).resolve().parents[1]


def prepare_with_probe(probe):
    def send(command):
        print(f"초기화: {command}", flush=True)
        lines, _ = probe.send(command, timeout_s=120)
        if (not lines or not is_ok(lines[-1][1]) or
                any(is_error(line) or line.lower().startswith("alarm") for _, line in lines)):
            raise RuntimeError(f"초기화 명령 실패: {command}")

    def settled(timeout):
        status, elapsed = probe.wait_settled(timeout)
        if elapsed is None or not status or state_of(status).lower() != "idle":
            raise RuntimeError("초기화 중 로봇 정지 확인 실패")
        return status

    for command in HOME_SEQUENCE:
        send(command)
        if command == "$H":
            settled(120)
    for _, command in parse_file(REPO / "trajectories/policy_start.gcode"):
        send(command)
        if command == "M4 S40":
            time.sleep(1)
        target = pose_of(command)
        if target is not None:
            status = settled(30)
            cart = find_field(fields(status), "Cartesian")
            if not cart or len(cart) < 6 or not all(math.isfinite(v) for v in cart[:6]):
                raise RuntimeError("초기 위치의 Cartesian 보고값이 올바르지 않습니다")
            delta_mm = math.dist(cart[:3], target[:3])
            delta_deg = max(abs((a-b+180) % 360-180) for a, b in zip(cart[3:6], target[3:6]))
            if delta_mm > 2 or delta_deg > 1:
                raise RuntimeError(f"초기 위치 도착 실패: {delta_mm:.2f} mm / {delta_deg:.2f} deg")
            probe.log("initial_pose_ready", cart6=cart[:6], gripper_s=40)
