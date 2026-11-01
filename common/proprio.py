"""Mirobot 상태 → LIBERO proprio 9칸 (W9 CHECKLIST 3-2, 10/28 결정).

실물 Mirobot 이 `?` 로 보고한 자세(플랜지 X Y Z mm · A B C 도)를, Panda 가 같은 자리에 있을 때의
`robot_states` 로 바꾼다 — [손가락 2, 파지점 위치 3 (m, LIBERO world), 쿼터니언 4 (**xyzw**)].
순서는 Cosmos LIBERO 로더 · `run_libero_eval.py:334` 와 같다.

* **자세** — `tools/poses_to_gcode.py` 의 역변환 검산과 같은 계산이다. G-code 를 만들 때(Panda → Mirobot)의
  점 · 짝 · 배율 · 공구 · 자세 모드를 그대로 써야 같은 자리로 돌아온다. 그 값은 G-code 머리말에 있다 (`settings_from_gcode`).
  Panda 쪽 기준(시작 자세)은 G-code 에 없어서 부르는 쪽이 준다 — 시뮬 reset 자세, 또는 손 좌표 기록의 meta
* **쿼터니언 부호** — q 와 −q 는 같은 자세지만 숫자는 다르다. LIBERO 데이터는 x 성분이 늘 양수 쪽으로 이어진다
  (체크포인트 통계 0.29 ~ 1.0, W9 시험판 1.0 근처). 변환한 값도 기준과 같은 쪽으로 맞춘다 (`align_sign`)
* **손가락** — B' (10/28): Mirobot `M4` 명령을 기준으로 하되 값은 Panda 뜻에 맞춘다. 열림 → Panda 열림 값,
  닫힘 → Panda 가 블록을 잡았을 때 값. 0 근처(빈손으로 끝까지 닫음)로 두면 Panda 데이터와 뜻이 반대가 된다.
  "잡음" 값은 시뮬 블록 크기에 따라 다르다 — 11/01 블록을 실물 20 mm ÷ 0.663 = 30.2 mm 로 바꿔 0.0140 으로 다시 쟀다
  (40 mm 블록 때는 0.0191). 블록 크기가 바뀌면 다시 잰다.
  닫히는 시간은 아직 모른다 — 여기서는 닫힌 정도(0 ~ 1)를 받는다

표준 라이브러리만 쓴다 (`common/` 규약).
"""

from __future__ import annotations

import re

from common.rotation import Quat, euler_xyz_deg_to_quat, mirobot_to_libero_quat, quat_mul, quat_wxyz_to_xyzw
from common.workspace import (
    LEGACY_POINT,
    Vec3,
    flange_to_grip,
    mirobot_to_libero_flange_m,
    read_pair_marker,
    read_point_marker,
    tool_of,
)

FINGER_OPEN_M = 0.0398  # Panda 열림 — W6 pick up red s0 approach·lower 0.0396 ~ 0.0399
FINGER_HOLD_M = 0.0140  # Panda 가 30.2 mm 블록을 잡았을 때 — W9 Panda 90개 lift·verify 중앙 (11/01, 40 mm 때 0.0191)

# 머리말 설명 줄 "; F = x축 180°, …, orientation absolute" (poses_to_gcode · libero_to_mirobot_gcode 둘 다 기본 absolute)
_ORIENTATION_RE = re.compile(r"^;.*\borientation\s+(absolute|relative)\b", re.MULTILINE)


def settings_from_gcode(text: str) -> dict:
    """G-code 본문 → 만들 때 쓴 변환 설정. 표시가 없으면 각 함수의 옛 파일 규칙을 따른다."""
    point = read_point_marker(text) or LEGACY_POINT
    tool = tool_of(text)
    ref_mirobot, scale = read_pair_marker(text, point, tool)
    m = _ORIENTATION_RE.search(text)
    return {"point": point, "tool_mm": tool, "ref_mirobot_mm": ref_mirobot, "scale": scale,
            "orientation": m.group(1) if m else "absolute"}


def align_sign(q: Quat, ref: Quat) -> Quat:
    """q 와 −q 중 `ref` 쪽 부호를 고른다 — 같은 자세, LIBERO 데이터와 같은 숫자."""
    return q if sum(a * b for a, b in zip(q, ref)) >= 0 else tuple(-v for v in q)


def mirobot_to_libero_pose(xyz_mm, abc_deg, ref_flange_m, ref_q_wxyz: Quat, settings: dict) -> tuple[Vec3, Quat]:
    """Mirobot 플랜지 자세(`?` 보고나 G0) → LIBERO 파지점 위치(m), 자세(wxyz, `ref_q_wxyz` 쪽 부호).

    `ref_flange_m` · `ref_q_wxyz` — G-code 를 만들 때 짝지은 Panda 시작 자세 (플랜지 위치, LIBERO 자세).
    """
    q_m = euler_xyz_deg_to_quat(*abc_deg)
    q_l = mirobot_to_libero_quat(q_m) if settings["orientation"] == "absolute" else quat_mul(q_m, ref_q_wxyz)
    flange = mirobot_to_libero_flange_m(xyz_mm, q_m, q_l, ref_flange_m, ref_q_wxyz, settings["point"],
                                        settings["scale"], settings["ref_mirobot_mm"], settings["tool_mm"])
    return flange_to_grip(flange, q_l), align_sign(q_l, ref_q_wxyz)


def fingers(closed: float, open_m: float = FINGER_OPEN_M, hold_m: float = FINGER_HOLD_M) -> tuple[float, float]:
    """B' — 닫힌 정도(0 열림 ~ 1 블록을 잡음) → Panda 손가락 두 칸 (왼쪽 +, 오른쪽 −)."""
    c = min(max(closed, 0.0), 1.0)
    q = open_m * (1.0 - c) + hold_m * c  # 끝점(0, 1)에서 열림·잡음 값이 정확히 나오게
    return q, -q


def robot_states(fingers_m, grip_pos_m, q_wxyz: Quat) -> list[float]:
    """LIBERO `robot_states` 9칸 — 손가락 2 + 파지점 위치 3 + 쿼터니언 4 (**xyzw**)."""
    return [*fingers_m, *grip_pos_m, *quat_wxyz_to_xyzw(q_wxyz)]
