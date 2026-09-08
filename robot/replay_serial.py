#!/usr/bin/env python3
"""임베디드 데모를 시리얼 G-code 로 실제 Mirobot 에 재생한다. (노트북 전용)

로봇 USB 케이블이 꽂힌 PC 에서 실행한다. HDF5 데이터셋은 필요 없고 pyserial 만
있으면 된다.

    python -m pip install pyserial

드라이런, 로봇에 아무 명령도 보내지 않음:

    python -m robot.replay_serial --demo all

실제 실행, 먼저 한 데모를 몇 스텝만:

    python -m robot.replay_serial --port COM7 --demo 0 --max-steps 10 --execute

실제 실행, demo_0 ~ demo_9:

    python -m robot.replay_serial --port COM7 --demo all --period 0.2 --home-each-demo --execute

궤적 데이터와 G-code 변환은 common/ 에 있다. 서버 쪽(server/replay_network.py)이
같은 데이터를 쓰므로 여기서 고치지 말 것.
"""

from __future__ import annotations

import argparse
import time

try:
    import serial
except ImportError:
    serial = None

from common.demos import DEMOS, parse_demo_selection
from common.gcode import (
    DEFAULT_CLOSE_CMD,
    DEFAULT_OPEN_CMD,
    DEFAULT_Z_OFFSET_MM,
    HOME_SEQUENCE,
    gripper_gcode,
    state_to_gcode,
)
from common.schema import TASK_INSTRUCTION


def send_gcode(ser, command: str, dry_run: bool) -> None:
    print(f"send: {command}")
    if dry_run:
        return

    ser.write((command + "\n").encode())
    while True:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line:
            print(f"  recv: {line}")
        low = line.lower()
        if low.startswith("error"):
            raise RuntimeError(f"Robot returned error for {command}: {line}")
        if "[reset to continue]" in low:
            ser.write(b"\n")
            raise RuntimeError("Robot is waiting for reset.")
        if "ok" in low:
            return


def run_home(ser, dry_run: bool) -> None:
    for command in HOME_SEQUENCE:
        send_gcode(ser, command, dry_run)


def replay_demo(ser, demo_idx: int, args, dry_run: bool) -> None:
    demo = DEMOS[str(demo_idx)]
    actions = demo["actions"]
    states = demo["states"]
    indices = list(range(0, len(states), args.stride))
    if args.max_steps > 0:
        indices = indices[: args.max_steps]

    print(f"===== demo_{demo_idx} | states={len(states)} | replayed={len(indices)} =====")
    last_gripper = None
    for step_idx in indices:
        state = states[step_idx]
        action = actions[step_idx]
        print(f"[demo_{demo_idx} step {step_idx:04d}]")
        send_gcode(
            ser,
            state_to_gcode(
                state,
                args.x_offset_mm,
                args.y_offset_mm,
                args.z_offset_mm,
                args.a_deg,
                args.b_deg,
                args.c_deg,
            ),
            dry_run,
        )

        grip_cmd = gripper_gcode(action, args.open_cmd, args.close_cmd)
        if grip_cmd != last_gripper:
            send_gcode(ser, grip_cmd, dry_run)
            last_gripper = grip_cmd

        if args.period > 0:
            time.sleep(args.period)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay embedded Mirobot demos.")
    parser.add_argument("--demo", default="all", help="Demo index, range like 0-9, or all. Default: all")
    parser.add_argument("--port", default="COM7", help="Serial port, e.g. COM7 or /dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--execute", action="store_true", help="Actually send commands. Without this, dry-run only.")
    parser.add_argument("--skip-home", action="store_true", help="Do not home before replay starts.")
    parser.add_argument("--home-each-demo", action="store_true", help="Home before every selected demo. Recommended for all demos.")
    parser.add_argument("--period", type=float, default=0.20, help="Seconds between states.")
    parser.add_argument("--between-demo-pause", type=float, default=1.0, help="Seconds to pause between demos.")
    parser.add_argument("--max-steps", type=int, default=0, help="Per-demo limit. 0 means replay all states.")
    parser.add_argument("--stride", type=int, default=1, help="Replay every Nth state.")
    parser.add_argument("--x-offset-mm", type=float, default=0.0)
    parser.add_argument("--y-offset-mm", type=float, default=0.0)
    parser.add_argument("--z-offset-mm", type=float, default=DEFAULT_Z_OFFSET_MM)
    parser.add_argument("--a-deg", type=float, default=0.0)
    parser.add_argument("--b-deg", type=float, default=0.0)
    parser.add_argument("--c-deg", type=float, default=0.0)
    parser.add_argument("--open-cmd", default=DEFAULT_OPEN_CMD)
    parser.add_argument("--close-cmd", default=DEFAULT_CLOSE_CMD)
    args = parser.parse_args()

    if args.stride < 1:
        parser.error("--stride must be >= 1")
    if args.period < 0 or args.between_demo_pause < 0:
        parser.error("--period and --between-demo-pause must be >= 0")

    selected = parse_demo_selection(args.demo)
    dry_run = not args.execute
    print(f"instruction: {TASK_INSTRUCTION}")
    print(f"available demos: {sorted(int(k) for k in DEMOS.keys())}")
    print(f"selected demos: {selected}")
    print(f"mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print(f"port: {args.port}")
    print(f"z_offset_mm: {args.z_offset_mm}")

    ser = None
    if args.execute:
        if serial is None:
            raise RuntimeError("pyserial is not installed. Run: python -m pip install pyserial")
        ser = serial.Serial(port=args.port, baudrate=args.baudrate, timeout=1)
        time.sleep(2)

    try:
        if not args.skip_home and not args.home_each_demo:
            run_home(ser, dry_run)

        for i, demo_idx in enumerate(selected):
            if args.home_each_demo and not args.skip_home:
                print(f"===== homing before demo_{demo_idx} =====")
                run_home(ser, dry_run)
            replay_demo(ser, demo_idx, args, dry_run)
            if i != len(selected) - 1 and args.between_demo_pause > 0:
                time.sleep(args.between_demo_pause)
    finally:
        if ser is not None:
            ser.close()
            print("serial closed")


if __name__ == "__main__":
    main()
