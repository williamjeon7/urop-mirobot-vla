#!/usr/bin/env python3
"""G-code 파일을 Mirobot 에 한 줄씩 보낸다. (로봇 노트북 전용 — 시리얼 직결)

`tools/libero_to_mirobot_gcode.py` 가 만든 파일을 실행한다. `G0` 마다 **멈춘 것을 확인한 뒤** 다음 줄로 가고,
줄마다 `?` 보고값을 남긴다. 그 기록이 Mirobot → LIBERO 방향(5-1)의 입력이 된다.

    python -m tools.run_gcode trajectories/2026_09_17-compound-relative.gcode --port COM4 --dry-run
    python -m tools.run_gcode trajectories/2026_09_17-compound-relative.gcode --port COM4

기본은 **줄마다 확인**이다 (Enter 보냄 / s 건너뜀 / q 중단). 익숙해지면 `--auto`.
전송·정지 판정·기록은 `tools/probe_mirobot.py` 의 `Probe` 를 그대로 쓴다 (9/13·9/17 실물에서 쓰인 코드).

**주의** — `--home` 을 주지 않으면 호밍하지 않는다. 파일의 첫 줄이 보통 홈 근처라, 로봇이 엉뚱한 자세에 있으면
첫 이동이 크다. 처음에는 `--dry-run` 으로 좌표를 보고, 비상정지에 손이 닿는 곳에서 시작할 것.
"""

from __future__ import annotations

import argparse
import math
import re
import time
from pathlib import Path

from common.gcode import HOME_SEQUENCE
from common.workspace import MIROBOT_HOME_MM
from tools.probe_mirobot import Probe, fields, find_field, fmt, is_error, serial, state_of

REACH_WARN_MM = 280.0  # 수평 거리. 도달 약 315mm — 여유를 둔다
ANGLE_WARN_DEG = 30.0
AXIS_LETTERS = "XYZABC"


def parse_file(path: Path) -> list[tuple[str, str]]:
    """(설명, 명령) 목록. ';' 줄은 바로 다음 명령의 설명으로 쓴다."""
    out, label = [], ""
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(";"):
            label = line.lstrip("; ").split("  (")[0].strip()[:20]  # "seg1-end  (step 55, hold)" → "seg1-end"
            continue
        out.append((label, line))
        label = ""
    return out


def pose_of(command: str) -> list[float] | None:
    """`G0 X.. Y.. Z.. A.. B.. C..` → [X, Y, Z, A, B, C]. G0 가 아니면 None."""
    if not command.upper().startswith("G0"):
        return None
    found = {m.group(1).upper(): float(m.group(2)) for m in re.finditer(r"([A-Za-z])(-?\d+(?:\.\d+)?)", command[2:])}
    return [found.get(letter, 0.0) for letter in AXIS_LETTERS] if set(AXIS_LETTERS) <= set(found) else None


def show_plan(entries) -> None:
    print(f"\n{'#':>2} {'설명':<12} | {'X':>8} {'Y':>8} {'Z':>8} | {'A':>7} {'B':>7} {'C':>7} | {'수평':>6} | {'홈에서':>7}")
    n = 0
    for label, command in entries:
        pose = pose_of(command)
        if pose is None:
            print(f"{'':2} {'[설정]':<12} | {command}")
            continue
        n += 1
        reach = math.hypot(pose[0], pose[1])
        from_home = math.dist(pose[:3], MIROBOT_HOME_MM)
        flags = []
        if reach > REACH_WARN_MM:
            flags.append(f"수평 {reach:.0f}mm")
        if max(abs(v) for v in pose[3:]) > ANGLE_WARN_DEG:
            flags.append("각도 큼")
        print(f"{n:2d} {label:<12} | {pose[0]:8.2f} {pose[1]:8.2f} {pose[2]:8.2f} | {pose[3]:7.2f} {pose[4]:7.2f} {pose[5]:7.2f}"
              f" | {reach:6.1f} | {from_home:6.1f}mm{'  !! ' + ', '.join(flags) if flags else ''}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gcode", type=Path)
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--auto", action="store_true", help="줄마다 묻지 않는다")
    parser.add_argument("--dry-run", action="store_true", help="보내지 않고 계획만 보여준다")
    parser.add_argument("--home", action="store_true", help="시작 전에 호밍 ($22=1 $H M20 G90) — 로봇이 크게 움직인다")
    parser.add_argument("--settle-timeout", type=float, default=20.0)
    parser.add_argument("--log-dir", default="data/gcode_run")
    args = parser.parse_args()

    entries = parse_file(args.gcode)
    moves = sum(1 for _, c in entries if pose_of(c) is not None)
    print(f"{args.gcode} — 명령 {len(entries)}줄 (이동 {moves}개)")
    show_plan(entries)
    if args.dry_run:
        print("\n--dry-run: 아무것도 보내지 않았다")
        return

    if serial is None:
        raise SystemExit("pyserial 이 없다: python -m pip install pyserial")
    if input(f"\n{args.port} 로 보낸다. 비상정지에 손이 닿는가? [y/N] ").strip().lower() != "y":
        print("취소")
        return

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{time.strftime('%Y%m%d_%H%M%S')}--{args.gcode.stem}.jsonl"
    ser = serial.Serial(port=args.port, baudrate=args.baudrate, timeout=0.05)
    probe = Probe(ser, log_path)
    time.sleep(2)  # 포트를 열면 보드가 리셋된다
    for _, line in probe.read_lines(0.5):
        print(f"  boot: {line}")
    probe.log("run_gcode_open", port=args.port, gcode=str(args.gcode), auto=args.auto)
    print(f"log: {log_path}")

    results = []
    try:
        if args.home:
            if input("호밍한다. 로봇이 크게 움직인다. 진행? [y/N] ").strip().lower() != "y":
                return
            for command in HOME_SEQUENCE:
                probe.send(command, timeout_s=60.0)

        index = 0
        for label, command in entries:
            pose = pose_of(command)
            if pose is None:  # G90, M20 같은 설정 줄
                print(f"\n[설정] {command}")
                probe.send(command)
                continue

            index += 1
            print(f"\n[{index}/{moves}] {label}  {command}")
            if not args.auto:
                answer = input("  보낼까? [Enter 보냄 / s 건너뜀 / q 중단] ").strip().lower()
                if answer == "q":
                    print("  중단")
                    break
                if answer == "s":
                    continue

            lines, _ = probe.send(command)
            if any(is_error(line) for _, line in lines):
                print("  !! 에러 — 멈춘다")
                break

            status_line, settle_s = probe.wait_settled(args.settle_timeout)
            reported = find_field(fields(status_line), "Cartesian") if status_line else None
            diff = [r - c for r, c in zip(reported[:6], pose)] if reported and len(reported) >= 6 else None
            print(f"  보고: {fmt(reported[:6] if reported else None)}  ({state_of(status_line) if status_line else '?'},"
                  f" {settle_s:.2f}s)" if status_line else "  보고 없음")
            if diff:
                print(f"  차이: {fmt([round(v, 3) for v in diff])}   위치 {math.dist(reported[:3], pose[:3]):.2f}mm")
            probe.log("waypoint", label=label, cmd=command, commanded=pose, reported=reported, settle_s=settle_s)
            results.append((label, pose, reported, settle_s))
    except KeyboardInterrupt:
        print("\n중단 — 로봇은 마지막 명령을 계속 수행할 수 있다")
    finally:
        ser.close()
        probe.log_file.close()

    print(f"\n{'설명':14} | {'위치 차이':>9} | {'자세 차이 (A B C)':>24} | {'정지까지':>7}")
    for label, pose, reported, settle_s in results:
        if not reported or len(reported) < 6:
            print(f"{label:14} | {'보고 없음':>9}")
            continue
        print(f"{label:14} | {math.dist(reported[:3], pose[:3]):8.2f}mm | "
              f"{', '.join(f'{r - c:+.2f}' for r, c in zip(reported[3:6], pose[3:6])):>24} | "
              f"{(f'{settle_s:.2f}s' if settle_s else '미정지'):>7}")
    print(f"\nlog: {log_path}")


if __name__ == "__main__":
    main()
