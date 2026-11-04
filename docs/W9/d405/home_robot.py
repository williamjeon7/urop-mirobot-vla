"""Home the Mirobot once and park it at the recording initial pose. No camera, no recording.

Teleop capture skips homing by default. Run this after power-on, after a collision,
or when the initial wrist view looks shifted; then record as usual.

    docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.home_robot --port COM3

The arm moves a lot during homing ($H): clear the workspace first. Do not run this
while a capture is open on the same port.
"""
from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from common.gcode import HOME_SEQUENCE
from tools.probe_mirobot import Probe, is_error, pose_summary

# Same initial pose as robot/inverse_kinematics.py, so the next capture starts in place.
INITIAL_POSE = 'G0 X198.67 Y0 Z230.72 A0 B0 C0'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', default='COM3', help='Mirobot serial port (not the D405)')
    args = parser.parse_args(argv)
    import serial
    log_dir = Path(tempfile.gettempdir())/'mirobot_home'  # outside the repo: no stray files
    log_dir.mkdir(exist_ok=True)
    ser = serial.Serial(port=args.port, baudrate=115200, timeout=0.05)
    probe = Probe(ser, log_dir/f"{time.strftime('%Y%m%d_%H%M%S')}.jsonl")
    try:
        time.sleep(2)  # same settling wait as the original controller
        probe.read_lines(0.5)
        for command in (*HOME_SEQUENCE, INITIAL_POSE):
            print('send:', command, flush=True)
            lines, elapsed = probe.send(command, timeout_s=120.0)
            if elapsed is None or is_error(lines[-1][1]):
                raise SystemExit(f'Robot did not acknowledge {command!r}; homing incomplete.')
        status, settled = probe.wait_settled(30.0)
        if settled is None:
            raise SystemExit('Robot did not settle at the initial pose.')
        print('Homed; at the initial pose:', pose_summary(status))
        print('Next: record with the usual capture command (it skips homing by default).')
    finally:
        ser.close()
        probe.log_file.close()


if __name__ == '__main__':
    main()
