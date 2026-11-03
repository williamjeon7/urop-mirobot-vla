"""`common/policy_io.py` 확인 테스트 (W10).

    python -m tests.test_policy_io

`apply_action` 은 `servo_action` 의 역이고, `libero_to_mirobot_pose` 는 `mirobot_to_libero_pose` 의 역이다.
녹화 데이터로 하는 검사는 `tools/check_policy_io.py` (docs/W10/POLICY_RUN.md 2절).
"""

from __future__ import annotations

import math
from pathlib import Path

from common.policy_io import apply_action, gripper_s, libero_to_mirobot_pose
from common.proprio import mirobot_to_libero_pose, settings_from_gcode
from common.rotation import FRAME_F, quat_from_axis_deg, quat_mul, quat_xyzw_to_wxyz
from common.servo import pose_gap, servo_action
from common.workspace import grip_to_flange

REPO = Path(__file__).resolve().parents[1]
GCODE = REPO / "trajectories" / "2026_10_11-w6-pickup-blue-s2-e5.gcode"
START_GRIP_M = (-0.2084646605658239, 0.0, 1.1732794757296405)  # pickup-*-s2 meta start_eef_pos
START_Q_XYZW = (0.9995966048795354, 0.00024621283188763776, -0.028400120485872867, -6.995295959032546e-06)


def test_apply_action_inverts_servo_action():
    """자르기가 없으면 현재 + servo_action(현재 → 목표) 는 목표다 (위치·자세 모두)."""
    p0, q0 = (0.1, -0.05, 1.0), quat_mul(quat_from_axis_deg("z", 10.0), FRAME_F)
    p1, q1 = (0.112, -0.043, 0.991), quat_mul(quat_from_axis_deg("y", 3.0), q0)
    a = servo_action(p0, q0, p1, q1, 1.0)
    assert max(abs(v) for v in a[:6]) < 1.0  # 자르기 없음
    p, q = apply_action(p0, q0, a)
    dp, dq = pose_gap(p, q, p1, q1)
    assert dp < 1e-12 and dq < 1e-9, (dp, dq)


def test_mirobot_round_trip():
    """Mirobot X Y Z A B C → LIBERO → Mirobot 이 제자리로 온다 (녹화 기준 G-code 머리말)."""
    settings = settings_from_gcode(GCODE.read_text(encoding="utf-8"))
    ref_q = quat_xyzw_to_wxyz(START_Q_XYZW)
    ref_flange = grip_to_flange(START_GRIP_M, ref_q)
    for cart in [(198.67, 0.0, 230.72, 0.0, 0.0, 0.0), (159.0, 60.0, 75.0, 0.0, 0.0, 0.0),
                 (180.0, -20.0, 120.0, 5.0, -3.0, 12.0)]:
        pos, q = mirobot_to_libero_pose(cart[:3], cart[3:], ref_flange, ref_q, settings)
        xyz, abc = libero_to_mirobot_pose(pos, q, ref_flange, ref_q, settings)
        assert math.dist(xyz, cart[:3]) < 1e-9, (xyz, cart)
        assert max(abs(a - b) for a, b in zip(abc, cart[3:])) < 1e-9, (abc, cart)


def test_gripper_s():
    assert gripper_s([0] * 6 + [1.0]) == 60.0 and gripper_s([0] * 6 + [-1.0]) == 40.0


if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            ran += 1
    print(f"\n{ran}개 통과")
