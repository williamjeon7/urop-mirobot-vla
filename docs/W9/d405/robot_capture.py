"""Ordered, stop-at-waypoint robot execution with continuous status polling.

Reuse the repository serial parser and Z floor. Never home automatically.
Only absolute, fully specified G0 moves and known setup/gripper/dwell lines
are accepted. Unlike run_gcode --stream, M4 stays between the right moves.
"""
from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path

from tools.probe_mirobot import Probe, fields, find_field, is_error, is_ok, state_of
from tools.run_gcode import Z_FLOOR_MM, low_lines, parse_file, pose_of


def validate_gcode(path: Path, z_floor: float = Z_FLOOR_MM):
    entries = parse_file(path)
    if not entries or entries[0][1].upper() != 'G90':
        raise ValueError('G-code must start with G90 (absolute coordinates).')
    if low_lines(entries, z_floor):
        raise ValueError(f'G-code is below flange Z floor {z_floor} mm.')
    for _, command in entries:
        command = command.upper()
        if command in ('G90', 'M20'):
            continue
        if re.fullmatch(r'M4\s+S\d+(?:\.\d+)?', command):
            continue
        if re.fullmatch(r'G4\s+P\d+(?:\.\d+)?', command):
            continue
        if pose_of(command) is not None and re.fullmatch(
            r'G0\s+X-?\d+(?:\.\d+)?\s+Y-?\d+(?:\.\d+)?\s+Z-?\d+(?:\.\d+)?'
            r'\s+A-?\d+(?:\.\d+)?\s+B-?\d+(?:\.\d+)?\s+C-?\d+(?:\.\d+)?', command
        ):
            continue
        raise ValueError(f'Unsupported command; nothing sent: {command}')
    return entries


def run_robot(port, entries, out, clock_ns, stop, gripper_seconds, initial_s,
              baud=115200, poll_hz=20.0, command_timeout=120.0):
    import serial

    with serial.Serial(port, baud, timeout=0.01, write_timeout=1) as ser, \
            (out / 'robot.jsonl').open('x', encoding='utf-8') as log:
        probe = Probe(ser, out / 'serial.jsonl')
        def emit(kind, **data):
            log.write(json.dumps(dict(kind=kind, t_s=(time.perf_counter_ns()-clock_ns)/1e9,
                                      **data)) + '\n')
            log.flush()

        def sample():
            if stop.is_set():
                raise RuntimeError('Capture stopped; no further robot commands sent.')
            query_start = (time.perf_counter_ns()-clock_ns)/1e9
            line, elapsed, others = probe.status(timeout_s=0.3, flush=False)
            for _, other in others:
                if is_error(other):
                    raise RuntimeError(f'Robot error: {other}')
            if line:
                cart = find_field(fields(line), 'Cartesian')
                if cart is None or len(cart) < 6 or not all(math.isfinite(v) for v in cart[:6]):
                    raise RuntimeError(f'Invalid Cartesian status: {line}')
                emit('state', cart=cart[:6], state=state_of(line),
                     query_start_s=query_start, rtt_s=elapsed)
            return line, any(is_ok(v) for _, v in others)

        def hold(seconds):
            end = time.perf_counter() + seconds
            while time.perf_counter() < end:
                begin = time.perf_counter()
                sample()
                stop.wait(max(0, 1/poll_hz - (time.perf_counter()-begin)))

        try:
            # Opening serial can reset some devices. Record status before sending.
            stop.wait(2)
            emit('gripper_initial', s=initial_s)
            hold(1)
            for label, command in entries:
                if stop.is_set():
                    raise RuntimeError('Capture stopped before command.')
                upper = command.upper()
                # G4 is implemented as a host hold; continue polling during dwell.
                if upper.startswith('G4'):
                    emit('dwell', cmd=command)
                    hold(float(upper.split('P', 1)[1]))
                    continue
                emit('command', cmd=command, label=label)
                ser.write((command + '\n').encode('ascii'))
                print('send:', command, flush=True)
                started, ack, recent = time.perf_counter(), False, []
                move = pose_of(upper)
                while True:
                    if time.perf_counter()-started > command_timeout:
                        raise TimeoutError(f'Robot command timeout: {command}')
                    begin = time.perf_counter()
                    line, ok = sample()
                    ack |= ok
                    if line:
                        cart = find_field(fields(line), 'Cartesian')[:6]
                        recent = (recent + [cart])[-3:]
                    if ack and move is None:
                        break
                    if (ack and line and len(recent) == 3 and recent[0] == recent[1] == recent[2]
                            and state_of(line).lower() == 'idle'):
                        if math.dist(cart[:3], move[:3]) > 2 or max(
                                abs((a-b+180) % 360-180) for a, b in zip(cart[3:], move[3:])) > 2:
                            raise RuntimeError('Idle pose differs from commanded waypoint (>2 mm/deg).')
                        break
                    stop.wait(max(0, 1/poll_hz - (time.perf_counter()-begin)))
                if upper.startswith('M4'):
                    # Timestamp is the send event; model servo travel separately offline.
                    hold(gripper_seconds)
            hold(1)
            emit('complete')
        finally:
            probe.log_file.close()
