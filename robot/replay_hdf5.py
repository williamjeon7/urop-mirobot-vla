#!/usr/bin/env python3
"""Replay a Mirobot HDF5 demonstration on the real robot via G-code.

The dataset stores EEF positions in MuJoCo world meters. This script converts
those positions to the Cartesian G-code convention used by the existing
robot/ scripts, then uses the action gripper command to open/close.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import h5py

try:
    import serial
except ImportError:  # pragma: no cover - lets --dry-run work without pyserial.
    serial = None

from common.gcode import (
    DEFAULT_CLOSE_CMD,
    DEFAULT_OPEN_CMD,
    HOME_SEQUENCE,
    gripper_gcode,
    state_to_gcode,
)


DEFAULT_HDF5 = (
    Path(__file__).resolve().parents[1]
    / "cosmos-policy"
    / "artifacts"
    / "mirobot"
    / "datasets"
    / "active"
    / "wrist_under_v1_pick_place"
    / "pick_up_the_red_cube_and_place_it_on_the_green_target_SCENE1_demos.hdf5"
)


def send_gcode(ser, command: str, dry_run: bool = False) -> bool:
    """Send one G-code command and wait for ok."""
    print(f"send: {command}")
    if dry_run:
        return True

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
            return True


def load_demo(hdf5_path: Path, demo_index: int):
    demo_key = f"demo_{demo_index}"
    with h5py.File(hdf5_path, "r") as file:
        if "data" not in file:
            raise ValueError(f"HDF5 has no /data group: {hdf5_path}")
        if demo_key not in file["data"]:
            available = ", ".join(sorted(file["data"].keys()))
            raise ValueError(f"{demo_key} not found. Available demos: {available}")

        demo = file[f"data/{demo_key}"]
        actions = demo["actions"][:]
        robot_states = demo["robot_states"][:]
        instruction = file["data"].attrs.get("task_instruction", "")
        if isinstance(instruction, bytes):
            instruction = instruction.decode("utf-8", errors="replace")

    if len(actions) != len(robot_states):
        raise ValueError(f"actions/state length mismatch: {len(actions)} vs {len(robot_states)}")
    return str(instruction), actions, robot_states


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hdf5", type=Path, default=DEFAULT_HDF5)
    parser.add_argument("--demo-index", type=int, default=0)
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--execute", action="store_true", help="Actually send G-code to the robot. Default is dry-run.")
    parser.add_argument("--skip-home", action="store_true", help="Do not run $22=1, $H, M20 before replay.")
    parser.add_argument("--period", type=float, default=0.10, help="Delay between replayed states in seconds.")
    parser.add_argument("--stride", type=int, default=1, help="Replay every Nth state.")
    parser.add_argument("--max-steps", type=int, default=0, help="Limit replayed states; 0 means all.")
    parser.add_argument("--x-offset-mm", type=float, default=0.0)
    parser.add_argument("--y-offset-mm", type=float, default=0.0)
    parser.add_argument(
        "--z-offset-mm",
        type=float,
        default=54.0,
        help="Offset from MuJoCo EEF z to real robot Cartesian Z. Default maps demo_0 initial z to 230.72mm.",
    )
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

    instruction, actions, robot_states = load_demo(args.hdf5.resolve(), args.demo_index)
    indices = list(range(0, len(robot_states), args.stride))
    if args.max_steps > 0:
        indices = indices[: args.max_steps]

    print(f"hdf5: {args.hdf5.resolve()}")
    print(f"demo: demo_{args.demo_index}")
    print(f"instruction: {instruction}")
    print(f"states: {len(robot_states)}, replayed: {len(indices)}, stride: {args.stride}")
    print(f"mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")

    ser = None
    if args.execute:
        if serial is None:
            raise RuntimeError("pyserial is not installed. Install it or run without --execute.")
        ser = serial.Serial(port=args.port, baudrate=args.baudrate, timeout=1)
        time.sleep(2)

    try:
        if not args.skip_home:
            for command in HOME_SEQUENCE:
                send_gcode(ser, command, dry_run=not args.execute)

        last_gripper_cmd: str | None = None
        for step_idx in indices:
            state = robot_states[step_idx]
            action = actions[step_idx]

            command = state_to_gcode(
                state,
                args.x_offset_mm,
                args.y_offset_mm,
                args.z_offset_mm,
                args.a_deg,
                args.b_deg,
                args.c_deg,
            )
            print(f"[demo_{args.demo_index} step {step_idx:04d}]")
            send_gcode(ser, command, dry_run=not args.execute)

            command = gripper_gcode(action, args.open_cmd, args.close_cmd)
            if command != last_gripper_cmd:
                send_gcode(ser, command, dry_run=not args.execute)
                last_gripper_cmd = command

            if args.period > 0:
                time.sleep(args.period)
    finally:
        if ser is not None:
            ser.close()


if __name__ == "__main__":
    main()
