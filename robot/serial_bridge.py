#!/usr/bin/env python3
"""TCP-to-serial bridge for WLKata Mirobot.

Run this on the Windows PC that has the Mirobot USB cable connected.

Install dependency:

    python -m pip install pyserial

Start bridge:

    python -m robot.serial_bridge --serial-port COM7

Then run a network replay script from the SSH server, pointing it at this PC's
IP address.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import time

try:
    import serial
except ImportError:
    serial = None

from common.protocol import (
    DEFAULT_BRIDGE_PORT,
    ERR_TOKEN,
    OK_TOKEN,
    PING_TOKEN,
    QUIT_TOKEN,
    READY_MESSAGE,
    STATUS_TOKEN,
)


STATUS_READ_TIMEOUT_S = 1.0
STATUS_M114_TIMEOUT_S = 1.5


def send_response(conn_file, line: str) -> None:
    conn_file.write((line + "\n").encode("utf-8"))
    conn_file.flush()


def send_to_robot(ser, command: str, timeout_s: float) -> list[str]:
    print(f"robot send: {command}", flush=True)
    ser.write((command + "\n").encode("utf-8"))

    deadline = time.monotonic() + timeout_s
    lines: list[str] = []
    while time.monotonic() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", errors="ignore").strip()
        if not line:
            continue

        print(f"robot recv: {line}", flush=True)
        lines.append(line)
        low = line.lower()
        if low.startswith("error"):
            raise RuntimeError(line)
        if "[reset to continue]" in low:
            ser.write(b"\n")
            raise RuntimeError("Robot is waiting for reset.")
        if "ok" in low:
            return lines

    raise TimeoutError(f"Timed out waiting for robot response to: {command}")


def read_robot_lines(ser, timeout_s: float, stop_on_ok: bool = False) -> list[str]:
    deadline = time.monotonic() + timeout_s
    lines: list[str] = []
    while time.monotonic() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", errors="ignore").strip()
        if not line:
            continue
        print(f"robot recv: {line}", flush=True)
        lines.append(line)
        low = line.lower()
        if low.startswith("error"):
            break
        if stop_on_ok and "ok" in low:
            break
    return lines


def query_robot_status(ser) -> dict:
    raw_lines: list[str] = []
    status = {
        "ok": False,
        "raw": raw_lines,
        "state": None,
        "mpos": None,
        "wpos": None,
        "joint": None,
        "gripper": None,
        "error": "",
    }

    try:
        ser.reset_input_buffer()
        print("robot status send: ?", flush=True)
        ser.write(b"?\n")
        raw_lines.extend(read_robot_lines(ser, STATUS_READ_TIMEOUT_S, stop_on_ok=False))

        parsed = parse_status_lines(raw_lines)
        status.update(parsed)

        has_angle_status = any(line.startswith("<") and line.endswith(">") for line in raw_lines)
        if status["mpos"] is None and status["wpos"] is None and not has_angle_status:
            print("robot status send: M114", flush=True)
            ser.write(b"M114\n")
            raw_lines.extend(read_robot_lines(ser, STATUS_M114_TIMEOUT_S, stop_on_ok=True))
            parsed = parse_status_lines(raw_lines)
            status.update({key: value for key, value in parsed.items() if value is not None})

        status["ok"] = bool(raw_lines) and not any(line.lower().startswith("error") for line in raw_lines)
        if not raw_lines:
            status["error"] = "No status response from robot for '?' or M114"
    except Exception as exc:
        status["error"] = str(exc)
    return status


def parse_status_lines(lines: list[str]) -> dict:
    parsed = {
        "state": None,
        "mpos": None,
        "wpos": None,
        "joint": None,
        "gripper": None,
    }
    for line in lines:
        if line.startswith("<") and line.endswith(">"):
            parse_grbl_angle_status(line, parsed)
        else:
            parse_m114_line(line, parsed)
    return parsed


def parse_grbl_angle_status(line: str, parsed: dict) -> None:
    body = line.strip("<>")
    if "Cartesian coordinate" in body:
        parse_mirobot_status_body(body, parsed)
        return

    parts = body.split("|")
    if parts and parts[0]:
        parsed["state"] = parts[0]
    for part in parts[1:]:
        if part.startswith("MPos:"):
            values = parse_float_list(part.removeprefix("MPos:"))
            if values:
                parsed["mpos"] = values[:3]
                if len(values) >= 6:
                    parsed["joint"] = values[3:6]
        elif part.startswith("WPos:"):
            values = parse_float_list(part.removeprefix("WPos:"))
            if values:
                parsed["wpos"] = values[:3]


def parse_mirobot_status_body(body: str, parsed: dict) -> None:
    state = body.split(",", 1)[0].strip()
    if state:
        parsed["state"] = state

    cartesian = re.search(r"Cartesian coordinate\(XYZ RxRyRz\):([^,]+),([^,]+),([^,]+)", body)
    if cartesian:
        parsed["mpos"] = [float(cartesian.group(i)) for i in range(1, 4)]

    angle = re.search(r"Angle\(ABCDXYZ\):([^,]+),([^,]+),([^,]+),([^,]+),([^,]+),([^,]+),([^,>]+)", body)
    if angle:
        parsed["joint"] = [float(angle.group(i)) for i in range(1, 8)]


def parse_m114_line(line: str, parsed: dict) -> None:
    axis_values = {
        match.group(1).upper(): float(match.group(2))
        for match in re.finditer(r"\b([XYZABC])\s*:?\s*(-?\d+(?:\.\d+)?)", line, re.IGNORECASE)
    }
    if all(axis in axis_values for axis in ("X", "Y", "Z")):
        position = [axis_values["X"], axis_values["Y"], axis_values["Z"]]
        if parsed["mpos"] is None:
            parsed["mpos"] = position
    joint_axes = ["A", "B", "C"]
    if all(axis in axis_values for axis in joint_axes):
        parsed["joint"] = [axis_values[axis] for axis in joint_axes]


def parse_float_list(text: str) -> list[float] | None:
    values: list[float] = []
    for item in text.split(","):
        try:
            values.append(float(item))
        except ValueError:
            return None
    return values or None


def handle_client(conn: socket.socket, addr, ser, robot_timeout_s: float) -> None:
    print(f"client connected: {addr}", flush=True)
    conn_file = conn.makefile("rwb", buffering=0)
    try:
        while True:
            raw = conn_file.readline()
            if not raw:
                print("client disconnected", flush=True)
                return

            command = raw.decode("utf-8", errors="ignore").strip()
            if not command:
                continue
            if command == QUIT_TOKEN:
                send_response(conn_file, OK_TOKEN)
                return
            if command == PING_TOKEN:
                send_response(conn_file, READY_MESSAGE)
                continue
            if command == STATUS_TOKEN:
                status = query_robot_status(ser)
                send_response(conn_file, json.dumps(status, ensure_ascii=False, separators=(",", ":")))
                if status["ok"]:
                    send_response(conn_file, OK_TOKEN)
                else:
                    send_response(conn_file, f"{ERR_TOKEN} {status['error']}")
                continue

            try:
                for line in send_to_robot(ser, command, robot_timeout_s):
                    send_response(conn_file, line)
                send_response(conn_file, OK_TOKEN)
            except Exception as exc:
                print(f"command failed: {exc}", flush=True)
                send_response(conn_file, f"{ERR_TOKEN} {exc}")
    finally:
        conn_file.close()
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Expose a local Mirobot serial port over TCP.")
    parser.add_argument("--serial-port", default="COM7", help="Windows serial port, e.g. COM7")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=DEFAULT_BRIDGE_PORT)
    parser.add_argument("--robot-timeout", type=float, default=20.0)
    args = parser.parse_args()

    if serial is None:
        raise RuntimeError("pyserial is not installed. Run: python -m pip install pyserial")

    print(f"opening serial: {args.serial_port} @ {args.baudrate}", flush=True)
    ser = serial.Serial(port=args.serial_port, baudrate=args.baudrate, timeout=1)
    time.sleep(2)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.listen_host, args.listen_port))
    server.listen(1)

    print(f"bridge listening on {args.listen_host}:{args.listen_port}", flush=True)
    print("press Ctrl+C to stop", flush=True)

    try:
        while True:
            conn, addr = server.accept()
            handle_client(conn, addr, ser, args.robot_timeout)
    finally:
        server.close()
        ser.close()
        print("bridge closed", flush=True)


if __name__ == "__main__":
    main()
