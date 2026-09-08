"""노트북 TCP 브리지에 붙는 클라이언트. (서버 전용)

robot/serial_bridge.py 가 반대편에서 이 프로토콜을 말한다. 토큰과 포트는
common/protocol.py 한 곳에서 가져오므로 여기서 상수를 새로 정의하지 말 것.
"""

from __future__ import annotations

import socket

from common.gcode import HOME_SEQUENCE
from common.protocol import ERR_TOKEN, LINE_ENCODING, OK_TOKEN, PING_TOKEN, QUIT_TOKEN


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
        self.file.write((command + "\n").encode(LINE_ENCODING))
        self.file.flush()

        while True:
            raw = self.file.readline()
            if not raw:
                raise RuntimeError("Bridge connection closed.")

            line = raw.decode(LINE_ENCODING, errors="ignore").strip()
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
    for command in HOME_SEQUENCE:
        send_gcode(client, command, dry_run)
