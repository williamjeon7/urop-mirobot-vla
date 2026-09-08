#!/usr/bin/env python3
"""demo_0 하나만 시리얼 G-code 로 재생한다. (노트북 전용)

첫 연결 확인용 최소 스크립트다. 전체 데모는 robot/replay_serial.py 를 쓴다.

    python -m robot.replay_demo0 --max-steps 10                      # 드라이런
    python -m robot.replay_demo0 --port COM7 --max-steps 10 --execute
    python -m robot.replay_demo0 --port /dev/ttyUSB0 --execute

재배치 전에는 이 파일이 demo_0 궤적 1,400여 줄을 자체 복사본으로 들고 있었다.
common.demos.DEMOS["0"] 과 값이 완전히 동일해서 공용 데이터를 참조하도록 바꿨다.
"""

from __future__ import annotations

import argparse
import time

try:
    import serial
except ImportError:
    serial = None

from common.demos import DEMOS
from common.gcode import (
    DEFAULT_CLOSE_CMD,
    DEFAULT_OPEN_CMD,
    DEFAULT_Z_OFFSET_MM,
    HOME_SEQUENCE,
    gripper_gcode,
    state_to_gcode,
)
from common.schema import TASK_INSTRUCTION
from robot.replay_serial import send_gcode

DEMO_INDEX = "0"


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay embedded Mirobot demo_0.")
    parser.add_argument("--port", default="COM7", help="Serial port, e.g. COM7 or /dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--execute", action="store_true", help="Actually send commands. Without this, dry-run only.")
    parser.add_argument("--skip-home", action="store_true")
    parser.add_argument("--period", type=float, default=0.20, help="Seconds between states.")
    parser.add_argument("--max-steps", type=int, default=0, help="0 means replay all states.")
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
    if args.period < 0:
        parser.error("--period must be >= 0")

    demo = DEMOS[DEMO_INDEX]
    states = demo["states"]
    actions = demo["actions"]

    indices = list(range(0, len(states), args.stride))
    if args.max_steps > 0:
        indices = indices[: args.max_steps]

    dry_run = not args.execute
    print(f"instruction: {TASK_INSTRUCTION}")
    print(f"demo_0 states: {len(states)}, replayed: {len(indices)}, stride: {args.stride}")
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
        if not args.skip_home:
            for command in HOME_SEQUENCE:
                send_gcode(ser, command, dry_run)

        last_gripper = None
        for step_idx in indices:
            state = states[step_idx]
            action = actions[step_idx]
            print(f"[step {step_idx:04d}]")
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
    finally:
        if ser is not None:
            ser.close()
            print("serial closed")


if __name__ == "__main__":
    main()
