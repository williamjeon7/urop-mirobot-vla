"""상태/액션 → Mirobot G-code 인코딩.

전송 방식(시리얼 직결이냐 TCP 브리지냐)과 무관한 순수 변환만 둔다.
실제 전송은 robot/ 과 server/ 가 각자 담당한다.
"""

from __future__ import annotations

from common.schema import ACTION_GRIPPER, STATE_EEF_POS_X, STATE_EEF_POS_Y, STATE_EEF_POS_Z

# MuJoCo world frame 원점과 로봇 베이스의 Z 차이 보정값 (mm).
DEFAULT_Z_OFFSET_MM = 54.0

# 그리퍼 기본 명령
DEFAULT_OPEN_CMD = "M4 S40"
DEFAULT_CLOSE_CMD = "M4 S60"

# 호밍 시퀀스. $H 는 로봇이 크게 움직이므로 주변을 비우고 실행할 것.
HOME_SEQUENCE = ("$22=1", "$H", "M20", "G90")


def state_to_gcode(
    state,
    x_offset_mm: float,
    y_offset_mm: float,
    z_offset_mm: float,
    a: float,
    b: float,
    c: float,
) -> str:
    """상태 벡터의 EEF 위치(meter)를 G0 직교 이동 명령(mm)으로 바꾼다."""
    x_mm = float(state[STATE_EEF_POS_X]) * 1000.0 + x_offset_mm
    y_mm = float(state[STATE_EEF_POS_Y]) * 1000.0 + y_offset_mm
    z_mm = float(state[STATE_EEF_POS_Z]) * 1000.0 + z_offset_mm
    return f"G0 X{x_mm:.2f} Y{y_mm:.2f} Z{z_mm:.2f} A{a:.2f} B{b:.2f} C{c:.2f}"


def gripper_gcode(action, open_cmd: str, close_cmd: str) -> str:
    """액션의 그리퍼 성분 부호로 열기/닫기 명령을 고른다."""
    return open_cmd if float(action[ACTION_GRIPPER]) < 0.0 else close_cmd
