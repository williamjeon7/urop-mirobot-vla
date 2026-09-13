#!/usr/bin/env python3
"""W2 실물 확인용 Mirobot 프로브. (노트북 전용)

docs/W2/CHECKLIST.md §4 "실물에서 확인할 것" 을 명령 하나씩으로 쪼갰다.
포트를 열면 보드가 리셋될 수 있으므로, 한 번 열어 둔 채 명령을 입력하는 대화형이다.
응답은 원문 그대로 찍고 data/probe/<시각>.jsonl 에 전부 남긴다.

    python -m tools.probe_mirobot --port COM7
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import statistics
import time
from pathlib import Path

try:
    import serial
except ImportError:
    serial = None

from common.gcode import HOME_SEQUENCE
from robot.serial_bridge import STATUS_READ_TIMEOUT_S, parse_status_lines

HELP = """\
  home                        $22=1 $H M20 G90 — 로봇이 크게 움직인다. 처음에 한 번
  raw [n]                     ? 원문 + 필드별 값 개수 + 현재 파서(serial_bridge) 결과
  grip <gcode...>             그리퍼 명령 1회 → 3초 뒤 ? 에서 바뀐 필드   예) grip M4 S40
  timing [n]                  ? 왕복 시간 n회 (기본 100)
  moving <dx_mm> [sec]        G0 을 보내고 ok 를 기다리지 않고 ? 폴링 — 이동 중 위치 보고 여부, ok 시점
  line <x|y|z> <len> <step>   EE 직선 이동, 스텝마다 관절각 기록 — 튀는 구간 탐지
  joint <X|Y|Z|A|B|C> <deg>   관절 모드로 한 축만 움직였다 되돌림 — Angle(ABCDXYZ) 순서 확인
  send <gcode...>             임의 명령
  help / quit"""

# label:숫자,숫자,... 한 덩어리. "Cartesian coordinate(XYZ RxRyRz):1,2,3" 처럼 괄호와 공백을 허용한다.
FIELD_RE = re.compile(
    r"([A-Za-z][A-Za-z_ ]*(?:\([^)]*\))?)\s*:\s*(-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?)*)"
)
JOINT_JUMP_WARN_DEG = 10.0  # line 에서 스텝 하나에 이보다 크게 변한 관절을 표시
MAX_MOVE_MM = 100.0
MAX_JOINT_DEG = 15.0


def is_ok(line: str) -> bool:
    return line.lower().startswith("ok")


def is_error(line: str) -> bool:
    low = line.lower()
    return low.startswith("error") or "reset to continue" in low


def is_status(line: str) -> bool:
    return line.startswith("<") and line.endswith(">")


def fields(status_line: str) -> dict[str, list[float]]:
    body = status_line.strip("<>")
    return {label.strip(): [float(v) for v in nums.split(",")] for label, nums in FIELD_RE.findall(body)}


def find_field(parsed: dict[str, list[float]], prefix: str) -> list[float] | None:
    for label, values in parsed.items():
        if label.lower().startswith(prefix.lower()):
            return values
    return None


def angle_letters(parsed: dict[str, list[float]]) -> str:
    for label in parsed:
        match = re.match(r"Angle\((\w+)\)", label)
        if match:
            return match.group(1)
    return ""


def state_of(status_line: str) -> str:
    return re.split(r"[,|]", status_line.strip("<>"), maxsplit=1)[0].strip()


def g0(pose: list[float]) -> str:
    x, y, z, a, b, c = pose
    return f"G0 X{x:.2f} Y{y:.2f} Z{z:.2f} A{a:.2f} B{b:.2f} C{c:.2f}"


def fmt(values: list[float] | None) -> str:
    return " ".join(f"{v:8.2f}" for v in values) if values else "-"


def clamp(value: float, limit: float) -> float:
    if abs(value) > limit:
        print(f"  {value} → ±{limit} 로 제한")
        return limit if value > 0 else -limit
    return value


def confirm(message: str) -> bool:
    return input(f"  {message}  실행? [y/N] ").strip().lower() == "y"


class Probe:
    def __init__(self, ser, log_path: Path):
        self.ser = ser
        self.log_file = log_path.open("a", encoding="utf-8")

    def log(self, kind: str, **data) -> None:
        record = {"t_wall": time.time(), "t_mono": time.monotonic(), "kind": kind, **data}
        self.log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.log_file.flush()

    # --- 저수준 ---

    def read_lines(self, timeout_s: float, until=None) -> list[tuple[float, str]]:
        """timeout_s 동안 줄을 모은다. until(line) 이 참이면 바로 멈춘다. [(monotonic, line)]"""
        deadline = time.monotonic() + timeout_s
        out: list[tuple[float, str]] = []
        pending = b""
        while time.monotonic() < deadline:
            chunk = self.ser.readline()
            if not chunk:
                continue
            pending += chunk
            if not pending.endswith(b"\n"):  # readline 이 타임아웃으로 줄 중간에서 끊겼다
                continue
            line = pending.decode("utf-8", errors="replace").strip()
            pending = b""
            if not line:
                continue
            out.append((time.monotonic(), line))
            if until is not None and until(line):
                break
        if pending.strip():
            out.append((time.monotonic(), pending.decode("utf-8", errors="replace").strip() + "  [잘림]"))
        return out

    def send(self, command: str, timeout_s: float = 30.0) -> tuple[list[tuple[float, str]], float | None]:
        """명령을 보내고 ok/error 까지 읽는다. (응답 줄, ok 까지 걸린 초)"""
        self.ser.reset_input_buffer()
        t0 = time.monotonic()
        self.ser.write((command + "\n").encode())
        lines = self.read_lines(timeout_s, until=lambda l: is_ok(l) or is_error(l))
        for _, line in lines:
            print(f"  recv: {line}")
        done = bool(lines) and (is_ok(lines[-1][1]) or is_error(lines[-1][1]))
        elapsed = lines[-1][0] - t0 if done else None
        if not done:
            print(f"  !! {timeout_s}s 안에 ok 없음")
        self.log("send", cmd=command, lines=[l for _, l in lines], elapsed_s=elapsed)
        return lines, elapsed

    def status(self, timeout_s: float = 1.0, flush: bool = True):
        """? 한 번. (상태 줄 또는 None, 걸린 초, 그 사이 받은 다른 줄 [(monotonic, line)])"""
        if flush:
            self.ser.reset_input_buffer()
        t0 = time.monotonic()
        self.ser.write(b"?\n")
        lines = self.read_lines(timeout_s, until=is_status)
        if lines and is_status(lines[-1][1]):
            return lines[-1][1], lines[-1][0] - t0, lines[:-1]
        return None, None, lines

    def current_pose(self) -> list[float] | None:
        status_line, _, _ = self.status()
        if status_line is None:
            print("  ? 응답 없음")
            return None
        cart = find_field(fields(status_line), "Cartesian")
        if cart is None or len(cart) < 6:
            print(f"  Cartesian 값이 6개가 아니다: {cart} — 자세를 몰라 이동 명령을 만들 수 없다")
            return None
        return cart[:6]

    def wait_settled(self, timeout_s: float = 15.0) -> tuple[str | None, float | None]:
        """Idle 이면서 위치·관절각이 3회 연속 같으면 멈춘 것으로 본다."""
        t0 = time.monotonic()
        recent: list[tuple] = []
        last = None
        while time.monotonic() - t0 < timeout_s:
            status_line, _, _ = self.status(flush=False)
            if status_line is None:
                continue
            last = status_line
            parsed = fields(status_line)
            recent = (recent + [(find_field(parsed, "Cartesian"), find_field(parsed, "Angle"))])[-3:]
            if len(recent) == 3 and recent[0] == recent[1] == recent[2] and state_of(status_line).lower() == "idle":
                return status_line, time.monotonic() - t0
            time.sleep(0.05)
        print(f"  !! {timeout_s}s 안에 멈추지 않음 (마지막: {last})")
        return last, None

    def move_and_poll(self, target: list[float], duration_s: float):
        """G0 을 보내고 ok 를 기다리지 않은 채 duration_s 동안 ? 를 폴링한다."""
        command = g0(target)
        self.ser.reset_input_buffer()
        t0 = time.monotonic()
        self.ser.write((command + "\n").encode())
        rows, ok_ms, misses = [], None, 0
        while time.monotonic() - t0 < duration_s:
            status_line, _, others = self.status(timeout_s=0.5, flush=False)
            for t, line in others:  # ok 는 다음 폴링에서 읽히므로 폴링 간격만큼 늦게 찍힌다
                if is_ok(line) and ok_ms is None:
                    ok_ms = round((t - t0) * 1000)
                elif is_error(line):
                    print(f"  !! {line}")
            if status_line is None:
                misses += 1
                continue
            parsed = fields(status_line)
            rows.append({
                "t_ms": round((time.monotonic() - t0) * 1000),
                "state": state_of(status_line),
                "cart": find_field(parsed, "Cartesian"),
                "angle": find_field(parsed, "Angle"),
            })
        self.log("moving", cmd=command, ok_ms=ok_ms, misses=misses, rows=rows)
        return command, ok_ms, misses, rows

    # --- 명령 ---

    def cmd_home(self, args: list[str]) -> None:
        if not confirm("$H 는 로봇이 크게 움직인다. 주변을 비웠나?"):
            return
        for command in HOME_SEQUENCE:
            print(f"send: {command}")
            self.send(command, timeout_s=120.0)

    def cmd_raw(self, args: list[str]) -> None:
        n = int(args[0]) if args else 1
        for i in range(n):
            self.ser.reset_input_buffer()
            t0 = time.monotonic()
            self.ser.write(b"?\n")
            lines = self.read_lines(1.5)  # 상태 줄에서 멈추지 않는다 — 뒤에 뭐가 더 오는지 본다
            print(f"--- ? #{i + 1}: {len(lines)}줄")
            for t, line in lines:
                print(f"  +{(t - t0) * 1000:6.1f}ms  {line!r}")
            for line in (l for _, l in lines if is_status(l)):
                print(f"  상태: {state_of(line)}")
                for label, values in fields(line).items():
                    print(f"  {label:<36} ({len(values)}개) {values}")
            print(f"  현재 파서 결과: {parse_status_lines([l for _, l in lines])}")
            self.log("raw", lines=[[round((t - t0) * 1000, 1), l] for t, l in lines])

    def cmd_grip(self, args: list[str]) -> None:
        if not args:
            print("  사용: grip M4 S40")
            return
        command = " ".join(args)
        before, _, _ = self.status()
        print(f"send: {command}")
        self.send(command)
        print("  3초 대기 — 그리퍼가 어디까지 가는지 눈으로 볼 것")
        time.sleep(3.0)
        after, _, _ = self.status()
        f_before = fields(before) if before else {}
        f_after = fields(after) if after else {}
        changed = [k for k in sorted(set(f_before) | set(f_after)) if f_before.get(k) != f_after.get(k)]
        for label in changed:
            print(f"  바뀜 {label}: {f_before.get(label)} → {f_after.get(label)}")
        if not changed:
            print("  ? 응답에서 바뀐 필드 없음")
        self.log("grip", cmd=command, before=before, after=after, changed=changed)

    def cmd_timing(self, args: list[str]) -> None:
        n = int(args[0]) if args else 100
        self.ser.reset_input_buffer()
        times: list[float] = []
        for _ in range(n):
            status_line, elapsed, _ = self.status(timeout_s=2.0, flush=False)
            if status_line is not None:
                times.append(elapsed)
        misses = n - len(times)
        self.log("timing", n=n, misses=misses, times_s=times)
        print(f"  응답 {len(times)}/{n}, 누락 {misses}")
        if times:
            s = sorted(times)
            median = statistics.median(s)
            p95 = s[min(len(s) - 1, int(len(s) * 0.95))]
            print(f"  min {s[0] * 1000:.1f} / median {median * 1000:.1f} / p95 {p95 * 1000:.1f} / max {s[-1] * 1000:.1f} ms")
            print(f"  → 로봇 응답 기준 상한 약 {1 / median:.1f} Hz")
        print(
            f"  참고: serial_bridge.query_robot_status 는 상태 줄을 받고도 "
            f"STATUS_READ_TIMEOUT_S={STATUS_READ_TIMEOUT_S}s 를 다 기다린다 → 지금 코드로는 1Hz 이하"
        )

    def cmd_moving(self, args: list[str]) -> None:
        dx = clamp(float(args[0]) if args else 30.0, MAX_MOVE_MM)
        duration_s = float(args[1]) if len(args) > 1 else 4.0
        start = self.current_pose()
        if start is None:
            return
        target = list(start)
        target[0] += dx
        if not confirm(f"{g0(start)}  →  {g0(target)}"):
            return
        command, ok_ms, misses, rows = self.move_and_poll(target, duration_s)
        print(f"send: {command}")
        print(f"  ok 수신: {f'+{ok_ms}ms' if ok_ms is not None else '폴링 중 안 옴'}  |  ? 응답 {len(rows)}회, 무응답 {misses}회")
        print(f"  {'t(ms)':>6}  {'state':<8} {'X':>8} {'Y':>8} {'Z':>8}   Angle")
        for row in rows:
            cart = row["cart"] or [float("nan")] * 3
            print(f"  {row['t_ms']:>6}  {row['state']:<8} {cart[0]:8.2f} {cart[1]:8.2f} {cart[2]:8.2f}   {fmt(row['angle'])}")
        lo, hi = sorted((start[0], target[0]))
        between = {round(r["cart"][0], 1) for r in rows if r["cart"] and lo + 0.5 < r["cart"][0] < hi - 0.5}
        if between:
            print(f"  → 이동 중 위치가 갱신된다 (중간 X 값 {len(between)}종)")
        else:
            print("  → 중간 위치가 안 보인다 — 정지 상태만 보고하거나, 이동 중 ? 에 응답하지 않거나, 이동이 폴링보다 빠르다")
        print("  시작 위치로 복귀")
        self.move_and_poll(start, duration_s)

    def cmd_line(self, args: list[str]) -> None:
        axis = args[0].lower()
        idx = "xyz".index(axis)
        length = clamp(float(args[1]), MAX_MOVE_MM)
        step = abs(float(args[2]))
        n_steps = int(abs(length) // step)
        start = self.current_pose()
        if start is None:
            return
        sign = 1.0 if length > 0 else -1.0
        if not confirm(f"{axis} 방향 {length}mm 를 {step}mm × {n_steps}스텝, 시작 {g0(start)}"):
            return

        rows = []
        prev_angle = None
        letters = ""
        for i in range(n_steps + 1):
            target = list(start)
            target[idx] += sign * step * i
            command = g0(target)
            print(f"send: {command}")
            lines, ok_s = self.send(command)
            if lines and is_error(lines[-1][1]):
                print("  에러 — 여기서 멈춘다 (도달 불가 좌표일 수 있다)")
                break
            status_line, settle_s = self.wait_settled()
            if status_line is None:
                break
            parsed = fields(status_line)
            letters = letters or angle_letters(parsed)
            angle = find_field(parsed, "Angle")
            jump = max((abs(a - b) for a, b in zip(angle, prev_angle)), default=0.0) if angle and prev_angle else 0.0
            prev_angle = angle or prev_angle
            rows.append({"i": i, "target": target, "cart": find_field(parsed, "Cartesian"), "angle": angle,
                         "jump_deg": jump, "ok_s": ok_s, "settle_s": settle_s})
        self.log("line", axis=axis, length=length, step=step, start=start, rows=rows)

        print(f"  {'i':>3} {'목표':>8} {'실측':>8}  max|Δ관절|   Angle({letters})")
        for row in rows:
            actual = row["cart"][idx] if row["cart"] else float("nan")
            flag = "  <-- 튐" if row["jump_deg"] > JOINT_JUMP_WARN_DEG else ""
            print(f"  {row['i']:>3} {row['target'][idx]:8.2f} {actual:8.2f}  {row['jump_deg']:9.2f}   {fmt(row['angle'])}{flag}")
        print(f"  스텝 {step}mm 에 관절이 {JOINT_JUMP_WARN_DEG}° 넘게 변하면 '튐' 표시. J5 범위(-180°~+40°)는 joint 로 순서를 확인한 뒤 읽을 것")
        print("  시작 위치로 복귀")
        self.send(g0(start))
        self.wait_settled()

    def cmd_joint(self, args: list[str]) -> None:
        letter = args[0].upper()
        if letter not in "XYZABC" or len(letter) != 1:
            print("  축은 X Y Z A B C 중 하나")
            return
        deg = clamp(float(args[1]), MAX_JOINT_DEG)
        if not confirm(f"관절 모드(M21) 상대 이동 G0 {letter}{deg:+.2f} 후 되돌림. 홈 근처에서만"):
            return
        before, _ = self.wait_settled()
        for command in ("M21", "G91", f"G0 {letter}{deg:.2f}"):
            print(f"send: {command}")
            self.send(command)
        moved, _ = self.wait_settled()
        for command in (f"G0 {letter}{-deg:.2f}", "G90", "M20"):
            print(f"send: {command}")
            self.send(command)
        after, _ = self.wait_settled()
        self.log("joint", letter=letter, deg=deg, before=before, moved=moved, after=after)
        if not (before and moved):
            return
        f_before, f_moved = fields(before), fields(moved)
        a_before, a_moved = find_field(f_before, "Angle"), find_field(f_moved, "Angle")
        letters = angle_letters(f_moved) or "?" * len(a_moved or [])
        print(f"  G0 {letter}{deg:+.2f} 에 대해 Angle({letters}) 변화:")
        for i, (b, m) in enumerate(zip(a_before or [], a_moved or [])):
            mark = "  <--" if abs(m - b) > 0.5 else ""
            label = letters[i] if i < len(letters) else "?"
            print(f"    [{i}] {label}: {b:8.2f} → {m:8.2f}{mark}")
        if after:
            print(f"  복귀 후 Angle: {fmt(find_field(fields(after), 'Angle'))}")

    def cmd_send(self, args: list[str]) -> None:
        command = " ".join(args)
        print(f"send: {command}")
        self.send(command, timeout_s=60.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive Mirobot probe for W2 hardware checks.")
    parser.add_argument("--port", default="COM7", help="Serial port, e.g. COM7")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--log-dir", default="data/probe")
    args = parser.parse_args()

    if serial is None:
        raise RuntimeError("pyserial is not installed. Run: python -m pip install pyserial")

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{time.strftime('%Y%m%d_%H%M%S')}.jsonl"

    ser = serial.Serial(port=args.port, baudrate=args.baudrate, timeout=0.05)
    probe = Probe(ser, log_path)
    time.sleep(2)  # 포트를 열면 보드가 리셋된다
    boot = probe.read_lines(0.5)
    for _, line in boot:
        print(f"  boot: {line}")
    probe.log("open", port=args.port, boot=[l for _, l in boot])
    print(f"log: {log_path}")
    print(HELP)

    commands = {
        "home": probe.cmd_home,
        "raw": probe.cmd_raw,
        "grip": probe.cmd_grip,
        "timing": probe.cmd_timing,
        "moving": probe.cmd_moving,
        "line": probe.cmd_line,
        "joint": probe.cmd_joint,
        "send": probe.cmd_send,
    }
    try:
        while True:
            try:
                entered = input("probe> ").strip()
            except EOFError:
                break
            if not entered:
                continue
            name, *rest = shlex.split(entered)
            if name in ("quit", "exit", "q"):
                break
            if name == "help":
                print(HELP)
                continue
            handler = commands.get(name)
            if handler is None:
                print("  모르는 명령. help")
                continue
            try:
                handler(rest)
            except KeyboardInterrupt:
                print("\n  중단 — 로봇은 마지막으로 받은 명령을 계속 수행할 수 있다")
            except (ValueError, IndexError) as exc:
                print(f"  인자 오류: {exc}")
    finally:
        ser.close()
        probe.log_file.close()
        print("serial closed")


if __name__ == "__main__":
    main()
