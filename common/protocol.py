"""노트북 브리지 ↔ 서버 통신 규약.

robot/serial_bridge.py 와 server/bridge_client.py 가 **같은 값을 써야** 한다.
재배치 전에는 양쪽 파일에 토큰이 복붙되어 있었고, 서버 쪽에만 STATUS_TOKEN 이
빠져 있었다. 그런 드리프트를 막으려고 여기 한 곳에 모았다.

한 줄 = 한 메시지, UTF-8, 개행으로 구분한다.

  서버 → 브리지 : G-code 한 줄, 또는 아래 제어 토큰
  브리지 → 서버 : OK_TOKEN [부가정보]  |  ERR_TOKEN <사유>
"""

from __future__ import annotations

# 브리지 응답 접두사
OK_TOKEN = "__OK__"
ERR_TOKEN = "__ERR__"

# 서버가 보내는 제어 토큰 (G-code 가 아님)
QUIT_TOKEN = "__QUIT__"
PING_TOKEN = "__PING__"
STATUS_TOKEN = "__STATUS__"

# 브리지가 PING 에 응답하는 문자열 (docs/SETUP_LINUX.md 의 연결 확인용)
READY_MESSAGE = f"{OK_TOKEN} bridge-ready"

DEFAULT_BRIDGE_PORT = 8765
DEFAULT_BRIDGE_HOST = "127.0.0.1"

LINE_ENCODING = "utf-8"

# 브리지 → 카메라 스트림 (robot/camera_bridge.py)
DEFAULT_CAMERA_PORT = 8890
