#!/usr/bin/env python3
"""G-code 파일을 Mirobot 에 한 줄씩 보낸다. (로봇 노트북 전용 — 시리얼 직결)

`tools/libero_to_mirobot_gcode.py` 가 만든 파일을 실행한다. `G0` 마다 **멈춘 것을 확인한 뒤** 다음 줄로 가고,
줄마다 `?` 보고값을 남긴다. 그 기록이 Mirobot → LIBERO 방향(5-1)의 입력이 된다.

    python -m tools.run_gcode trajectories/2026_09_17-compound-relative.gcode --port COM4 --dry-run
    python -m tools.run_gcode trajectories/2026_09_17-compound-relative.gcode --port COM4

기본은 **줄마다 확인**이다 (Enter 보냄 / s 건너뜀 / q 중단). 익숙해지면 `--auto`.
전송·정지 판정·기록은 `tools/probe_mirobot.py` 의 `Probe` 를 그대로 쓴다 (9/13·9/17 실물에서 쓰인 코드).

**세 가지 모드** — 멈추느냐, 무엇을 남기느냐가 다르다.

| | 묻나 | waypoint 마다 멈추나 | 남는 기록 |
|---|---|---|---|
| 기본 | 줄마다 | 예 | waypoint 마다 정지 자세 하나 |
| `--auto` | 아니오 | 예 | waypoint 마다 정지 자세 하나 |
| `--stream` | 아니오 | **아니오 — 이어서 흐른다** | **움직이는 내내 시간 찍힌 자세** (수십 Hz) |

`--stream` 이 성립하는 근거 둘, 모두 9/13 실물에서 확인한 것이다 (`docs/W2/CHECKLIST.md` 719줄).

1. `G0` 의 `ok` 는 **도착이 아니라 접수** 신호다 — ≤66ms 에 오는데 이동은 ≈1.15s 걸린다.
   그래서 `ok` 만 보고 다음 줄을 보내면 펌웨어 버퍼에 쌓여 멈추지 않고 이어진다.
   버퍼가 차면 `ok` 가 늦게 오면서 **저절로 속도가 맞는다** (GRBL 의 send-response 흐름 제어)
2. `?` 는 **실시간 명령**이라 버퍼를 쓰지 않고 즉시 답한다 — 30mm 이동 1.15s 동안 **89회, 무응답 0**.
   움직이는 중에도 계속 받을 수 있다

그래서 멈추지 않으면서 기록도 남는다. 다만 **자세의 성격이 다르다.**

- `--auto` 는 **도착해서 선** 자세다. 명령값과 바로 대 볼 수 있어 5-1 변환 검증의 입력이 된다
- `--stream` 은 **지나가는 중**의 자세다. 버퍼가 이어 붙이며 모서리를 깎으므로 waypoint 를 정확히 밟지 않는다.
  끝에 waypoint 마다 **가장 가까이 지나간 거리**를 찍어 준다 — 그 값이 모서리가 얼마나 깎였는지다

변환이 맞는지 보려면 `--auto`, 실제로 쓰는 모습(연속 동작·연속 기록)을 보려면 `--stream`.

**`--stream` 주의** — 보낸 줄은 취소되지 않는다. 중간에 `Ctrl-C` 를 눌러도 이미 버퍼에 들어간 이동은 끝까지 간다.
처음 보는 궤적은 `--auto` 로 먼저 돌려 보고 나서 쓸 것.

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
from tools.probe_mirobot import Probe, fields, find_field, fmt, is_error, is_ok, serial, state_of

REACH_WARN_MM = 280.0  # 수평 거리. 도달 약 315mm — 여유를 둔다
ANGLE_WARN_DEG = 30.0
AXIS_LETTERS = "XYZABC"


def parse_file(path: Path) -> list[tuple[str, str]]:
    """(설명, 명령) 목록. ';' 줄은 바로 다음 명령의 설명으로 쓴다."""
    out, label = [], ""
    for raw in path.read_text(encoding="utf-8").splitlines():
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


def run_stream(probe, entries, moves: int, poll_timeout: float, settle_timeout: float,
               poll_hz: float = 20.0) -> int:
    """멈추지 않고 보내면서 `?` 로 계속 받는다. 보낸 줄 수를 돌려준다.

    한 바퀴마다 (1) 보낼 줄이 남았고 앞 줄의 `ok` 가 왔으면 한 줄 쓰고, (2) `?` 를 한 번 물어 기록한다.
    `ok` 를 기다렸다 보내는 것이 GRBL 의 흐름 제어다 — 버퍼가 차면 `ok` 가 늦어지며 저절로 맞춰진다.
    `?` 는 버퍼를 쓰지 않으므로 그 사이에 끼워 넣어도 이동에 영향이 없다.

    기록 속도는 `poll_hz` 로 묶는다. 기본 20Hz 는 **LIBERO 제어 주기와 같은 값**이라, 나중에 이 기록을
    그대로 시뮬 쪽과 스텝 단위로 맞춰 볼 수 있다. 포트가 허용하는 만큼 물으면 훨씬 빠르지만
    (9/13 실물 77Hz) 그만큼 쓸모가 있는 것은 아니다.
    """
    moves_todo = [(label, command, pose) for label, command in entries
                  if (pose := pose_of(command)) is not None]
    samples, sent, misses, recent = [], [], 0, []
    index, awaiting_ok, failed, done_at = 0, False, None, None
    period = 1.0 / poll_hz if poll_hz > 0 else 0.0
    slot = 0  # 고정 격자의 몇 번째 칸을 기다리는 중인가
    t0 = time.perf_counter()

    while True:
        if not awaiting_ok and index < len(moves_todo):
            label, command, pose = moves_todo[index]
            probe.ser.write((command + "\n").encode())
            index += 1
            t_send = time.perf_counter() - t0
            sent.append({"index": index, "label": label, "commanded": pose, "t_s": round(t_send, 4)})
            probe.log("stream_send", index=index, label=label, cmd=command, commanded=pose, t_s=t_send)
            print(f"[{index}/{moves}] +{t_send:6.2f}s  {label:<14} {command}")
            awaiting_ok = True

        # 고정 격자 t0 + k·period 에 맞춰 묻는다. "마지막 샘플 + period" 로 재면 왕복 시간 T 가 매번 더해져
        # 주기가 period + T 가 된다 (9/21 실물에서 20Hz 설정이 9.3Hz 로 찍힌 원인).
        if period:
            now = time.perf_counter() - t0
            slot = max(slot, int(now / period) + 1)  # 못 따라가면 빈 칸은 건너뛴다
            wait = slot * period - now
            if wait > 0:
                time.sleep(wait)
        status_line, _, others = probe.status(timeout_s=poll_timeout, flush=False)
        for _, line in others:
            if is_ok(line):
                awaiting_ok = False
            elif is_error(line):
                failed = line
        if failed:
            print(f"  !! {failed} — 보내기를 멈춘다 (버퍼에 든 이동은 계속 간다)")
            break

        if status_line is None:
            misses += 1
            continue
        parsed = fields(status_line)
        cart, angle = find_field(parsed, "Cartesian"), find_field(parsed, "Angle")
        row = {"t_s": round(time.perf_counter() - t0, 4), "state": state_of(status_line),
               "cart": cart, "angle": angle}
        samples.append(row)  # 샘플마다 log() 하면 write+flush 가 루프에 들어간다 — 끝에 한 번 쓴다

        # 다 보냈으면 마지막 이동이 끝나기를 기다린다 — 판정은 wait_settled 와 같다
        recent = (recent + [(cart, angle)])[-3:]
        if index >= len(moves_todo) and not awaiting_ok:
            if done_at is None:
                done_at = time.perf_counter()
            if len(recent) == 3 and recent[0] == recent[1] == recent[2] \
                    and state_of(status_line).lower() == "idle":
                break
            if time.perf_counter() - done_at > settle_timeout:
                print(f"  !! 다 보내고 {settle_timeout}s 안에 멈추지 않았다 (마지막: {status_line})")
                break

    total_s = time.perf_counter() - t0
    probe.log("stream", total_s=total_s, poll_hz=poll_hz, misses=misses, sent=sent, rows=samples)
    hz = len(samples) / total_s if total_s else 0.0
    gaps = [b["t_s"] - a["t_s"] for a, b in zip(samples, samples[1:])]
    spread = (f"  간격 {min(gaps)*1000:.0f}~{max(gaps)*1000:.0f}ms, 중앙 "
              f"{sorted(gaps)[len(gaps)//2]*1000:.0f}ms" if gaps else "")
    print(f"\n{len(samples)}개 자세를 받았다 — {total_s:.1f}s 동안 {hz:.1f}Hz (무응답 {misses}회){spread}")
    if poll_hz > 0 and hz < poll_hz * 0.8:
        print(f"  !! {poll_hz:.0f}Hz 를 못 맞췄다 — `?` 왕복이 {1000/poll_hz:.0f}ms 보다 오래 걸린다는 뜻이다")

    print_closest(sent, samples)
    return index


def print_closest(sent, samples) -> None:
    """waypoint 마다 **가장 가까이 지나간 곳**. 위치와 자세를 따로 센다.

    지나가는 중의 기록이라 waypoint 를 정확히 밟지 않는다 — 버퍼가 이어 붙이며 모서리를 깎기 때문이다.
    위치와 자세를 섞어 하나의 수로 만들려면 "1° 를 몇 mm 로 칠까" 를 정해야 하는데 근거가 없어서, 따로 센다.
    홈 근처 waypoint 들처럼 **XYZ 가 같고 각도만 다른** 구간에서는 위치 열이 0 이고 자세 열이 정보를 갖는다.

    명령을 보낸 순서대로 실행되므로, 찾는 구간도 앞 waypoint 가 가장 가까웠던 시점 뒤로만 본다.
    그렇게 하지 않으면 XYZ 가 같은 waypoint 들이 서로의 샘플을 집는다.
    """
    usable = [r for r in samples if r["cart"] and len(r["cart"]) >= 6]
    print(f"\n{'설명':14} | {'보낸 때':>7} | {'위치':>9} {'그때':>7} | {'자세':>8} {'그때':>7}")
    start = 0
    for mark in sent:
        window = [(i, r) for i, r in enumerate(usable) if i >= start and r["t_s"] >= mark["t_s"]]
        if not window:
            print(f"{mark['label']:14} | {mark['t_s']:6.2f}s | {'기록 없음':>9}")
            continue
        i_pos, best_pos = min(window, key=lambda ir: math.dist(ir[1]["cart"][:3], mark["commanded"][:3]))
        i_rot, best_rot = min(window, key=lambda ir: max(abs(r - c) for r, c
                                                         in zip(ir[1]["cart"][3:6], mark["commanded"][3:6])))
        print(f"{mark['label']:14} | {mark['t_s']:6.2f}s | "
              f"{math.dist(best_pos['cart'][:3], mark['commanded'][:3]):6.2f}mm {best_pos['t_s']:6.2f}s | "
              f"{max(abs(r - c) for r, c in zip(best_rot['cart'][3:6], mark['commanded'][3:6])):6.2f}° "
              f"{best_rot['t_s']:6.2f}s")
        start = max(start, i_pos, i_rot)  # 뒤 waypoint 는 둘 다 지난 뒤에서만 찾는다
    print("\n두 열은 **모서리가 얼마나 깎였는지**다 — 0 에 가까우면 그 waypoint 를 거의 밟고 지나갔다는 뜻.")
    print("변환 검증에 쓸 '도착해서 선' 자세가 필요하면 --auto 로 다시 돌린다")



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gcode", type=Path)
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--auto", action="store_true", help="줄마다 묻지 않는다")
    parser.add_argument("--stream", action="store_true",
                        help="멈추지 않고 연달아 보내면서 `?` 로 계속 자세를 받는다 (실제 운용에 가까운 모습)")
    parser.add_argument("--poll-timeout", type=float, default=0.3, help="--stream 에서 `?` 한 번을 기다리는 초")
    parser.add_argument("--poll-hz", type=float, default=20.0,
                        help="--stream 기록 속도. 기본 20Hz 는 LIBERO 제어 주기와 같다. 0 이면 상한 없음")
    parser.add_argument("--dry-run", action="store_true", help="보내지 않고 계획만 보여준다")
    parser.add_argument("--home", action="store_true", help="시작 전에 호밍 ($22=1 $H M20 G90) — 로봇이 크게 움직인다")
    parser.add_argument("--settle-timeout", type=float, default=20.0)
    parser.add_argument("--log-dir", default="data/gcode_run")
    args = parser.parse_args()

    if args.stream:
        args.auto = True

    entries = parse_file(args.gcode)
    moves = sum(1 for _, c in entries if pose_of(c) is not None)
    print(f"{args.gcode} — 명령 {len(entries)}줄 (이동 {moves}개)"
          f"{'  [stream — 멈추지 않고 이어서, 보고값 안 남음]' if args.stream else ''}")
    show_plan(entries)
    if args.dry_run:
        print("\n--dry-run: 아무것도 보내지 않았다")
        return

    if serial is None:
        raise SystemExit("pyserial 이 없다: python -m pip install pyserial")
    if args.stream:
        print("\n!! stream: 보낸 줄은 취소되지 않는다. Ctrl-C 를 눌러도 버퍼에 들어간 이동은 끝까지 간다")
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

        if args.stream:
            for _, command in entries:  # G90, M20 같은 설정 줄을 먼저
                if pose_of(command) is None:
                    print(f"[설정] {command}")
                    probe.send(command)
            index = run_stream(probe, entries, moves, args.poll_timeout, args.settle_timeout, args.poll_hz)
            print(f"\n{index}개 이동을 보냈다\nlog: {log_path}")
            return

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
