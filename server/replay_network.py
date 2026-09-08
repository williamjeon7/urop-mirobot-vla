#!/usr/bin/env python3
"""TCP 브리지를 통해 임베디드 데모를 재생한다. (서버 전용)

노트북에서 robot/serial_bridge.py 를 먼저 띄운 뒤 서버에서 실행한다.
3창 구성과 역터널 설정은 docs/SETUP_LINUX.md 참조.

드라이런, 소켓을 아예 열지 않음(연결 테스트로는 쓸 수 없다):

    python -m server.replay_network --demo 0 --max-steps 10

실제 실행:

    python -m server.replay_network --bridge-host 127.0.0.1 --demo 0 --max-steps 10 --execute
    python -m server.replay_network --bridge-host 127.0.0.1 --demo all --home-each-demo --execute
"""

from __future__ import annotations

import argparse
import time

from common.demos import DEMOS, parse_demo_selection
from common.gcode import (
    DEFAULT_CLOSE_CMD,
    DEFAULT_OPEN_CMD,
    DEFAULT_Z_OFFSET_MM,
    gripper_gcode,
    state_to_gcode,
)
from common.protocol import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT
from common.schema import TASK_INSTRUCTION
from server.bridge_client import BridgeClient, run_home, send_gcode


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
    parser.add_argument("--bridge-host", default=DEFAULT_BRIDGE_HOST, help="Windows PC IP address")
    parser.add_argument("--bridge-port", type=int, default=DEFAULT_BRIDGE_PORT)
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
