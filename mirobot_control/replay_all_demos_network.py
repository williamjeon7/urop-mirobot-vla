#!/usr/bin/env python3
"""Replay embedded Mirobot demos through a TCP serial bridge.

Run ``mirobot_serial_bridge.py`` on the Windows PC connected to the robot, then
run this file on the SSH server.

Dry-run, no network commands:

    python replay_all_demos_network.py --demo 0 --max-steps 10

Real execution through the Windows bridge:

    python replay_all_demos_network.py --bridge-host <LAPTOP_IP> --demo 0 --max-steps 10 --execute
    python replay_all_demos_network.py --bridge-host <LAPTOP_IP> --demo all --home-each-demo --execute
"""

from __future__ import annotations

import argparse
import socket
import time

from replay_all_demos_standalone import (
    DEFAULT_Z_OFFSET_MM,
    DEMOS,
    TASK_INSTRUCTION,
    gripper_gcode,
    parse_demo_selection,
    state_to_gcode,
)


OK_TOKEN = "__OK__"
ERR_TOKEN = "__ERR__"
QUIT_TOKEN = "__QUIT__"
PING_TOKEN = "__PING__"


class BridgeClient:
    def __init__(self, host: str, port: int, timeout_s: float) -> None:
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self.sock: socket.socket | None = None
        self.file = None

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout_s)
        self.file = self.sock.makefile("rwb", buffering=0)
        self.send_command(PING_TOKEN, echo=False)

    def close(self) -> None:
        if self.file is not None:
            try:
                self.send_command(QUIT_TOKEN, echo=False)
            except OSError:
                pass
            self.file.close()
            self.file = None
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def send_command(self, command: str, echo: bool = True) -> None:
        if self.file is None:
            raise RuntimeError("Bridge is not connected.")

        if echo:
            print(f"send: {command}")
        self.file.write((command + "\n").encode("utf-8"))
        self.file.flush()

        while True:
            raw = self.file.readline()
            if not raw:
                raise RuntimeError("Bridge connection closed.")

            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            if line.startswith(OK_TOKEN):
                return
            if line.startswith(ERR_TOKEN):
                raise RuntimeError(line)
            if echo:
                print(f"  recv: {line}")


def send_gcode(client: BridgeClient | None, command: str, dry_run: bool) -> None:
    print(f"send: {command}")
    if dry_run:
        return
    if client is None:
        raise RuntimeError("Bridge client is not connected.")
    client.send_command(command, echo=False)


def run_home(client: BridgeClient | None, dry_run: bool) -> None:
    for command in ("$22=1", "$H", "M20", "G90"):
        send_gcode(client, command, dry_run)


def replay_demo(client: BridgeClient | None, demo_idx: int, args, dry_run: bool) -> None:
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
            client,
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
            send_gcode(client, grip_cmd, dry_run)
            last_gripper = grip_cmd

        if args.period > 0:
            time.sleep(args.period)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay embedded Mirobot demos through a TCP bridge.")
    parser.add_argument("--demo", default="all", help="Demo index, range like 0-9, or all. Default: all")
    parser.add_argument("--bridge-host", default="127.0.0.1", help="Windows PC IP address")
    parser.add_argument("--bridge-port", type=int, default=8765)
    parser.add_argument("--bridge-timeout", type=float, default=20.0)
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
    parser.add_argument("--open-cmd", default="M4 S40")
    parser.add_argument("--close-cmd", default="M4 S60")
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
    print(f"bridge: {args.bridge_host}:{args.bridge_port}")
    print(f"z_offset_mm: {args.z_offset_mm}")

    client = None
    if args.execute:
        client = BridgeClient(args.bridge_host, args.bridge_port, args.bridge_timeout)
        client.connect()

    try:
        if not args.skip_home and not args.home_each_demo:
            run_home(client, dry_run)

        for i, demo_idx in enumerate(selected):
            if args.home_each_demo and not args.skip_home:
                print(f"===== homing before demo_{demo_idx} =====")
                run_home(client, dry_run)
            replay_demo(client, demo_idx, args, dry_run)
            if i != len(selected) - 1 and args.between_demo_pause > 0:
                time.sleep(args.between_demo_pause)
    finally:
        if client is not None:
            client.close()
            print("bridge connection closed")


if __name__ == "__main__":
    main()
