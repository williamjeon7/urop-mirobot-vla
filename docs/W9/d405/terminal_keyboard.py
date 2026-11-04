"""Key events from a Linux/SSH terminal, without /dev/input or root access."""
from __future__ import annotations

import os
import select
import sys


class TerminalKeyboard:
    # Brackets are alternatives when the terminal/editor intercepts F8/F9.
    sequences = {
        b'\x1b[A': 'up', b'\x1b[B': 'down',
        b'\x1b[C': 'right', b'\x1b[D': 'left',
        b'\x1bOA': 'up', b'\x1bOB': 'down',
        b'\x1bOC': 'right', b'\x1bOD': 'left',
        b'\x1b[19~': 'f8', b'\x1b[20~': 'f9', b'\x1b[21~': 'f10',
    }

    def __init__(self, stream=None):
        self.stream = sys.stdin if stream is None else stream
        self.pending = b''
        self.keys = set()
        self.saved = None

    def __enter__(self):
        import termios
        import tty
        if not self.stream.isatty():
            raise ValueError('Teleop needs an interactive terminal (SSH: use ssh -t).')
        self.fd = self.stream.fileno()
        self.saved = termios.tcgetattr(self.fd)
        try:
            tty.setcbreak(self.fd)
            termios.tcflush(self.fd, termios.TCIFLUSH)
        except BaseException:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
            raise
        return self

    def __exit__(self, *exc):
        import termios
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)

    def poll(self):
        self.keys.clear()
        while select.select([self.fd], [], [], 0)[0]:
            data = os.read(self.fd, 4096)
            if not data:
                raise EOFError('Teleop terminal disconnected.')
            self.pending += data
        while self.pending:
            if self.pending.startswith(b'\x1b'):
                for sequence, key in self.sequences.items():
                    if self.pending.startswith(sequence):
                        self.keys.add(key)
                        self.pending = self.pending[len(sequence):]
                        break
                else:
                    if any(s.startswith(self.pending) for s in self.sequences):
                        return  # Complete a fragmented escape sequence next tick.
                    # Discard an unsupported escape sequence as a whole, so its
                    # digits cannot accidentally become joint-control keys.
                    import re
                    match = re.match(rb'\x1b(?:\[[0-?]*[ -/]*[@-~]|O.)', self.pending)
                    if not match and self.pending.startswith((b'\x1b[', b'\x1bO')):
                        return
                    self.pending = self.pending[match.end() if match else min(2, len(self.pending)):]
                    continue
                continue
            char = chr(self.pending[0]).lower()
            self.pending = self.pending[1:]
            if char in 'wasd123456789qfvg':
                self.keys.add(char)
            elif char in '[]':
                self.keys.add('f8' if char == '[' else 'f9')

    def is_pressed(self, key):
        if key in self.keys:
            self.keys.remove(key)
            return True
        return False
