"""`common/servo.py` 확인 테스트.

목표를 고정하고 매 스텝 다시 계산하는 방식(docs/W3/CONTROL.md 3절 ③)의 계산 부분만 본다.
시뮬은 쓰지 않는다 — 실제로 수렴하는지는 tools 쪽 루프에서 확인한다.

    python -m tests.test_servo
"""

from __future__ import annotations

import math

from common.rotation import IDENTITY, euler_xyz_deg_to_quat, quat_from_axis_deg
from common.servo import POS_SCALE_M, ROT_SCALE_RAD, fit_to_unit, pose_gap, reached, servo_action


def test_goal_lands_on_target():
    """50mm 안이면 컨트롤러 목표(`현재 + 액션 × 0.05`)가 정확히 우리 목표가 된다."""
    cur, target = (0.1, 0.2, 0.3), (0.13, 0.18, 0.32)
    a = servo_action(cur, IDENTITY, target, IDENTITY)
    goal = [c + v * POS_SCALE_M for c, v in zip(cur, a[:3])]
    assert max(abs(g - t) for g, t in zip(goal, target)) < 1e-12, goal


def test_direction_kept_when_too_far():
    """100mm·20mm 처럼 멀면 1 을 넘는다 — 성분마다 자르지 않고 전체를 줄여 방향을 지킨다."""
    cur, target = (0.0, 0.0, 0.0), (0.1, 0.02, 0.0)
    a = servo_action(cur, IDENTITY, target, IDENTITY)
    assert abs(max(abs(v) for v in a[:3]) - 1.0) < 1e-12          # 가장 큰 성분이 1
    assert abs(a[1] / a[0] - 0.2) < 1e-12                          # 비율 유지 (성분별로 잘랐다면 0.4)
    clipped = [min(1.0, max(-1.0, (t - c) / POS_SCALE_M)) for c, t in zip(cur, target)]
    assert abs(clipped[1] / clipped[0] - 0.4) < 1e-12              # 잘랐을 때는 방향이 틀어진다


def test_rotation_action():
    q_target = quat_from_axis_deg("z", 10.0)
    a = servo_action((0, 0, 0), IDENTITY, (0, 0, 0), q_target)
    assert abs(a[5] - math.radians(10.0) / ROT_SCALE_RAD) < 1e-9   # z 칸만
    assert max(abs(v) for v in a[3:5]) < 1e-12
    assert a[6] == -1.0                                            # 그리퍼는 열림 고정


def test_minus_q_gives_same_action():
    """목표를 −q 로 줘도 같다 — 부호는 오차 함수 안에서 맞춘다 (ROTATION.md 7절)."""
    cur = euler_xyz_deg_to_quat(0.0, 0.0, 178.0)
    target = euler_xyz_deg_to_quat(0.0, 0.0, -178.0)
    a = servo_action((0, 0, 0), cur, (0, 0, 0), target)
    b = servo_action((0, 0, 0), cur, (0, 0, 0), tuple(-v for v in target))
    assert max(abs(x - y) for x, y in zip(a, b)) < 1e-12
    assert abs(math.degrees(math.sqrt(sum((v * ROT_SCALE_RAD) ** 2 for v in a[3:6]))) - 4.0) < 1e-6  # 356° 가 아니라 4°


def test_gap_and_reached():
    cur, target = (0.0, 0.0, 0.0), (0.0015, 0.0, 0.0)
    q_target = quat_from_axis_deg("x", 0.5)
    gap_pos, gap_rot = pose_gap(cur, IDENTITY, target, q_target)
    assert abs(gap_pos - 0.0015) < 1e-12 and abs(gap_rot - 0.5) < 1e-9
    assert reached(cur, IDENTITY, target, q_target)                        # 2mm·1° 안
    assert not reached(cur, IDENTITY, (0.01, 0, 0), IDENTITY)              # 위치가 멀다
    assert not reached(cur, IDENTITY, target, quat_from_axis_deg("x", 3))  # 자세가 멀다


def test_fit_to_unit():
    assert fit_to_unit((0.5, -0.2, 0.0)) == (0.5, -0.2, 0.0)   # 1 이하면 그대로
    assert fit_to_unit((2.0, -1.0, 0.0)) == (1.0, -0.5, 0.0)


if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"ok  {name}"); ran += 1
    print(f"\n{ran}개 통과")
