"""`common/workspace.py` 확인 테스트.

    python -m tests.test_workspace
"""

from __future__ import annotations

import math

from common.rotation import (
    FRAME_F,
    euler_xyz_deg_to_quat,
    libero_to_mirobot_quat,
    mirobot_to_libero_quat,
    quat_conj,
    quat_from_axis_deg,
    quat_mul,
)
from common.workspace import (
    LEGACY_POINT,
    MIROBOT_HOME_GRIP_MM,
    MIROBOT_HOME_MM,
    flange_to_grip,
    grip_to_flange,
    libero_to_mirobot_flange_mm,
    libero_to_mirobot_xyz_mm,
    mirobot_flange_to_grip_mm,
    mirobot_grip_to_flange_mm,
    mirobot_to_libero_flange_m,
    mirobot_to_libero_xyz_m,
    point_marker,
    read_point_marker,
)

# 9/17 libero_90[7] 안정 후 플랜지 위치 (m, 월드) — 값 자체보다 "기준점" 역할이다
PANDA_START_FLANGE_M = (-0.2185, 0.0135, 1.2735)
# Panda 시작 자세 — 3.28° 기운 top-down (LIBERO_AXES.md 1절 크기). 파지점 기준을 시험할 때 쓴다
PANDA_START_QUAT = quat_mul(quat_from_axis_deg("y", 3.28), FRAME_F)
IDENTITY = (1.0, 0.0, 0.0, 0.0)


def close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_reference_maps_to_home():
    assert close(libero_to_mirobot_xyz_mm(PANDA_START_FLANGE_M, PANDA_START_FLANGE_M), MIROBOT_HOME_MM)


def test_axes_and_units():
    """월드 축이 같다 — 앞(+x)은 X+, 왼쪽(+y)은 Y+, 위(+z)는 Z+. m → mm."""
    x0, y0, z0 = PANDA_START_FLANGE_M
    hx, hy, hz = MIROBOT_HOME_MM
    assert close(libero_to_mirobot_xyz_mm((x0 + 0.06, y0, z0), PANDA_START_FLANGE_M), (hx + 60, hy, hz))
    assert close(libero_to_mirobot_xyz_mm((x0, y0 + 0.06, z0), PANDA_START_FLANGE_M), (hx, hy + 60, hz))
    assert close(libero_to_mirobot_xyz_mm((x0, y0, z0 - 0.04), PANDA_START_FLANGE_M), (hx, hy, hz - 40))


def test_scale_applies_to_displacement_only():
    x0, y0, z0 = PANDA_START_FLANGE_M
    out = libero_to_mirobot_xyz_mm((x0 + 0.1, y0 - 0.02, z0), PANDA_START_FLANGE_M, scale=0.5)
    assert close(out, (MIROBOT_HOME_MM[0] + 50, MIROBOT_HOME_MM[1] - 10, MIROBOT_HOME_MM[2]))


def test_round_trip():
    p = (-0.15, 0.08, 1.21)
    for scale in (1.0, 0.37):
        mm = libero_to_mirobot_xyz_mm(p, PANDA_START_FLANGE_M, scale=scale)
        assert close(mirobot_to_libero_xyz_m(mm, PANDA_START_FLANGE_M, scale=scale), p, 1e-12)


# ── 파지점 기준 (9/30) ────────────────────────────────────────

def test_mirobot_home_grip_is_55mm_below():
    """홈 (0,0,0) 에서 공구 축은 정확히 아래 — 파지점은 플랜지 바로 아래 55mm."""
    assert close(MIROBOT_HOME_GRIP_MM, (198.67, 0.0, 175.72))
    assert close(mirobot_flange_to_grip_mm(MIROBOT_HOME_MM, IDENTITY), MIROBOT_HOME_GRIP_MM)
    assert close(mirobot_grip_to_flange_mm(MIROBOT_HOME_GRIP_MM, IDENTITY), MIROBOT_HOME_MM)


def test_mirobot_grip_sign():
    """부호 고정 — Mirobot 규약의 공구 축은 −z 다. Mirobot 쿼터니언을 `flange_to_grip` 에 그대로 넣으면 위로 간다.

    B+20° 는 LIBERO Δry+ 와 같은 쪽 — 그리퍼가 뒤(−x)를 향한다 (LIBERO_AXES.md 3절 `(−sinθ, 0, −cosθ)`).
    """
    q = euler_xyz_deg_to_quat(0.0, 20.0, 0.0)
    grip = mirobot_flange_to_grip_mm((0.0, 0.0, 0.0), q)
    s, c = math.sin(math.radians(20)), math.cos(math.radians(20))
    assert close(grip, (-55 * s, 0.0, -55 * c))
    wrong = flange_to_grip((0.0, 0.0, 0.0), q, 55.0)  # 규약을 안 바꾸면 이렇게 된다 — 정확히 반대
    assert close(wrong, tuple(-v for v in grip))


def test_grip_reference_maps_to_home_grip():
    """Panda 시작 ↔ Mirobot 홈 짝. relative 면 Mirobot 이 홈 그대로, absolute 면 파지점만 홈에 있고 3.28° 기운다."""
    q_rel = quat_mul(PANDA_START_QUAT, quat_conj(PANDA_START_QUAT))  # relative — 시작으로부터의 회전 = 항등
    out = libero_to_mirobot_flange_mm(PANDA_START_FLANGE_M, PANDA_START_QUAT, q_rel,
                                      PANDA_START_FLANGE_M, PANDA_START_QUAT)
    assert close(out, MIROBOT_HOME_MM)

    q_abs = libero_to_mirobot_quat(PANDA_START_QUAT)
    out = libero_to_mirobot_flange_mm(PANDA_START_FLANGE_M, PANDA_START_QUAT, q_abs,
                                      PANDA_START_FLANGE_M, PANDA_START_QUAT)
    assert close(mirobot_flange_to_grip_mm(out, q_abs), MIROBOT_HOME_GRIP_MM)
    assert not close(out, MIROBOT_HOME_MM, 1e-3)  # 기울어진 만큼 플랜지는 홈에서 비켜난다


def test_grip_stays_when_panda_turns_about_grip():
    """Panda 가 파지점을 중심으로 돌면(OSC) Mirobot 도 파지점이 제자리 — 플랜지는 55mm 짜리 호를 그린다.

    ANSWER ① 6절 — 16.59° 에서 Panda 플랜지 27.7mm, Mirobot 플랜지 15.7mm.
    """
    top_down = FRAME_F
    start_grip = flange_to_grip(PANDA_START_FLANGE_M, top_down)
    tilt = quat_mul(quat_from_axis_deg("y", 16.59), top_down)  # 월드 y 둘레 — 왼쪽 곱
    p_flange = grip_to_flange(start_grip, tilt)
    q_mirobot = libero_to_mirobot_quat(tilt)  # 시작이 정확히 top-down 이라 absolute = relative
    out = libero_to_mirobot_flange_mm(p_flange, tilt, q_mirobot, PANDA_START_FLANGE_M, top_down)
    assert close(mirobot_flange_to_grip_mm(out, q_mirobot), MIROBOT_HOME_GRIP_MM)
    assert abs(math.hypot(out[0] - MIROBOT_HOME_MM[0], out[1] - MIROBOT_HOME_MM[1]) - 15.70) < 0.01
    assert abs(math.dist(p_flange, PANDA_START_FLANGE_M) * 1000 * math.cos(math.radians(16.59 / 2))
               - 27.70) < 0.05  # Panda 쪽 수평 몫


def test_grip_round_trip():
    """나갔다 들어오면 제자리 — absolute·relative, 스케일 둘 다. (왕복은 `L` 오차를 못 잡는다는 뜻이기도 하다)"""
    p = (-0.15, 0.08, 1.21)
    q_libero = quat_mul(euler_xyz_deg_to_quat(12.0, -7.0, 25.0), PANDA_START_QUAT)
    for q_mirobot, back in ((libero_to_mirobot_quat(q_libero), mirobot_to_libero_quat),
                            (quat_mul(q_libero, quat_conj(PANDA_START_QUAT)),
                             lambda q: quat_mul(q, PANDA_START_QUAT))):
        for scale in (1.0, 0.37):
            mm = libero_to_mirobot_flange_mm(p, q_libero, q_mirobot, PANDA_START_FLANGE_M, PANDA_START_QUAT,
                                             scale=scale)
            got = mirobot_to_libero_flange_m(mm, q_mirobot, back(q_mirobot), PANDA_START_FLANGE_M,
                                             PANDA_START_QUAT, scale=scale)
            assert close(got, p, 1e-12)


def test_flange_mode_unchanged():
    """`point="flange"` 는 9/28 까지의 변환 그대로 — 자세와 무관하게 플랜지 변위만 옮긴다."""
    p = (-0.15, 0.08, 1.21)
    q_libero = quat_mul(euler_xyz_deg_to_quat(12.0, -7.0, 25.0), PANDA_START_QUAT)
    q_mirobot = libero_to_mirobot_quat(q_libero)
    mm = libero_to_mirobot_flange_mm(p, q_libero, q_mirobot, PANDA_START_FLANGE_M, PANDA_START_QUAT,
                                     point="flange", scale=0.8)
    assert close(mm, libero_to_mirobot_xyz_mm(p, PANDA_START_FLANGE_M, scale=0.8))
    back = mirobot_to_libero_flange_m(mm, q_mirobot, q_libero, PANDA_START_FLANGE_M, PANDA_START_QUAT,
                                      point="flange", scale=0.8)
    assert close(back, mirobot_to_libero_xyz_m(mm, PANDA_START_FLANGE_M, scale=0.8))


def test_point_marker():
    """새 파일은 머리말에 점을 적고, 표시가 없는 옛 파일은 플랜지로 읽는다."""
    for point in ("grip", "flange"):
        assert read_point_marker(f"; LIBERO → Mirobot\n{point_marker(point)}\nG90\n") == point
    old = "; F = x축 180°, 플랜지 ↔ 플랜지, scale 1.0, orientation absolute\nG90\nM20\n"
    assert read_point_marker(old) is None and LEGACY_POINT == "flange"


if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            ran += 1
    print(f"\n{ran}개 통과")
