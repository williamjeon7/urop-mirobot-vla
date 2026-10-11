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
    LEGACY_TOOL_MM,
    MIROBOT_TOOL_MM,
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
    MAPPINGS,
    mirobot_home_mm,
    pair_marker,
    point_marker,
    read_pair_marker,
    read_point_marker,
    resolve_mapping,
    tool_marker,
    tool_of,
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

def test_mirobot_home_grip():
    """홈 (0,0,0) 에서 공구 좌표 = 월드 축 — 파지점은 플랜지에서 앞 15mm, 아래 55mm (10/11).

    10/11 전에는 앞 15mm 를 몰라 플랜지 바로 아래로 잡았다 (`LEGACY_TOOL_MM`).
    """
    assert MIROBOT_TOOL_MM == (15.0, 0.0, -55.0)
    assert close(MIROBOT_HOME_GRIP_MM, (213.67, 0.0, 175.72))
    assert close(mirobot_flange_to_grip_mm(MIROBOT_HOME_MM, IDENTITY), MIROBOT_HOME_GRIP_MM)
    assert close(mirobot_grip_to_flange_mm(MIROBOT_HOME_GRIP_MM, IDENTITY), MIROBOT_HOME_MM)
    assert close(mirobot_home_mm("grip", LEGACY_TOOL_MM), (198.67, 0.0, 175.72))


def test_mirobot_grip_sign():
    """부호 고정 — Mirobot 규약의 공구 축은 −z 다. Mirobot 쿼터니언을 `flange_to_grip` 에 그대로 넣으면 위로 간다.

    B+20° 는 LIBERO Δry+ 와 같은 쪽 — 그리퍼가 뒤(−x)를 향한다 (LIBERO_AXES.md 3절 `(−sinθ, 0, −cosθ)`).
    """
    q = euler_xyz_deg_to_quat(0.0, 20.0, 0.0)
    grip = mirobot_flange_to_grip_mm((0.0, 0.0, 0.0), q, LEGACY_TOOL_MM)  # 축 방향만 — 부호를 보려고
    s, c = math.sin(math.radians(20)), math.cos(math.radians(20))
    assert close(grip, (-55 * s, 0.0, -55 * c))
    wrong = flange_to_grip((0.0, 0.0, 0.0), q, 55.0)  # 규약을 안 바꾸면 이렇게 된다 — 정확히 반대
    assert close(wrong, tuple(-v for v in grip))


def test_tool_offset_turns_with_the_gripper():
    """앞 15mm 는 월드 X 고정이 아니라 집게에 붙어 돈다 — 집게를 90° 돌리면 왼쪽(+Y), 기울이면 높이에도 섞인다."""
    turned = mirobot_flange_to_grip_mm((0.0, 0.0, 0.0), euler_xyz_deg_to_quat(0.0, 0.0, 90.0))
    assert close(turned, (0.0, 15.0, -55.0))
    s, c = math.sin(math.radians(20)), math.cos(math.radians(20))
    tilted = mirobot_flange_to_grip_mm((0.0, 0.0, 0.0), euler_xyz_deg_to_quat(0.0, 20.0, 0.0))
    assert close(tilted, (15 * c - 55 * s, 0.0, -15 * s - 55 * c))
    q = euler_xyz_deg_to_quat(12.0, -7.0, 33.0)
    assert close(mirobot_grip_to_flange_mm(mirobot_flange_to_grip_mm((1.0, 2.0, 3.0), q), q), (1.0, 2.0, 3.0))


def test_tool_marker_and_legacy_files():
    """새 파일은 머리말에 `; tool …` 을 적는다. 없는 파지점 파일(9/30~10/11)은 축 방향 55mm 로 읽는다."""
    assert tool_of(f"; point grip\n{tool_marker()}\nG90\n") == MIROBOT_TOOL_MM
    assert tool_of("; point grip\nG90\n") == LEGACY_TOOL_MM
    assert read_pair_marker("; point grip\nG90\n", "grip", LEGACY_TOOL_MM) == ((198.67, 0.0, 175.72), 1.0)


def test_legacy_tool_reads_old_gcode_back():
    """옛 파일은 옛 벡터로 읽어야 되돌아온다 — 새 벡터로 읽으면 짝이 같아도 파지점이 15mm 어긋난다."""
    p = (-0.17, -0.04, 1.20)
    q_libero = quat_mul(quat_from_axis_deg("x", 6.0), PANDA_START_QUAT)
    q_m = libero_to_mirobot_quat(q_libero)
    ref_old = mirobot_home_mm("grip", LEGACY_TOOL_MM)
    old = libero_to_mirobot_flange_mm(p, q_libero, q_m, PANDA_START_FLANGE_M, PANDA_START_QUAT,
                                      "grip", 0.663, ref_old, LEGACY_TOOL_MM)
    back = mirobot_to_libero_flange_m(old, q_m, q_libero, PANDA_START_FLANGE_M, PANDA_START_QUAT,
                                      "grip", 0.663, ref_old, LEGACY_TOOL_MM)
    assert close(back, p, 1e-12)
    wrong = mirobot_to_libero_flange_m(old, q_m, q_libero, PANDA_START_FLANGE_M, PANDA_START_QUAT,
                                       "grip", 0.663, ref_old)  # 짝은 옛 값인데 벡터만 새 값
    assert abs(math.dist(wrong, p) * 1000 * 0.663 - 15.0) < 0.5


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
    # ANSWER 의 15.7mm 는 축 방향 55mm 만 있을 때의 값이다 — 옛 벡터로 확인한다
    out = libero_to_mirobot_flange_mm(p_flange, tilt, q_mirobot, PANDA_START_FLANGE_M, top_down,
                                      tool=LEGACY_TOOL_MM)
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


def test_pair_maps_start_to_pair():
    """짝을 옮기면 Panda 시작 자세가 그 짝(파지점)으로 간다 — 홈이 아니다 (10/1)."""
    pair = (120.0, 0.0, MIROBOT_HOME_GRIP_MM[2])
    q_mirobot = libero_to_mirobot_quat(PANDA_START_QUAT)
    mm = libero_to_mirobot_flange_mm(PANDA_START_FLANGE_M, PANDA_START_QUAT, q_mirobot,
                                     PANDA_START_FLANGE_M, PANDA_START_QUAT, ref_mirobot_mm=pair)
    assert close(mirobot_flange_to_grip_mm(mm, q_mirobot), pair)
    # 짝을 안 주면 예전 그대로 홈
    mm_home = libero_to_mirobot_flange_mm(PANDA_START_FLANGE_M, PANDA_START_QUAT, q_mirobot,
                                          PANDA_START_FLANGE_M, PANDA_START_QUAT)
    assert close(mirobot_flange_to_grip_mm(mm_home, q_mirobot), MIROBOT_HOME_GRIP_MM)


def test_pair_and_scale_round_trip():
    """후보 짝·배율로 나갔다 들어와도 제자리 — 짝을 옮겨도 변위는 짝을 중심으로 늘고 준다."""
    ref, scale = resolve_mapping("candidate", "grip")
    p = (-0.05, 0.22, 1.05)
    q_libero = quat_mul(euler_xyz_deg_to_quat(10.0, -5.0, 30.0), PANDA_START_QUAT)
    q_mirobot = libero_to_mirobot_quat(q_libero)
    mm = libero_to_mirobot_flange_mm(p, q_libero, q_mirobot, PANDA_START_FLANGE_M, PANDA_START_QUAT,
                                     scale=scale, ref_mirobot_mm=ref)
    got = mirobot_to_libero_flange_m(mm, q_mirobot, q_libero, PANDA_START_FLANGE_M, PANDA_START_QUAT,
                                     scale=scale, ref_mirobot_mm=ref)
    assert close(got, p, 1e-12)
    # 파지점 변위는 정확히 배율만큼 줄어 짝에 더해진다
    d_panda = [(a - b) * 1000 for a, b in zip(flange_to_grip(p, q_libero),
                                               flange_to_grip(PANDA_START_FLANGE_M, PANDA_START_QUAT))]
    grip = mirobot_flange_to_grip_mm(mm, q_mirobot)
    assert close(grip, [r + scale * d for r, d in zip(ref, d_panda)], 1e-9)


def test_pair_marker():
    """새 파일은 짝·배율을 머리말에 적고, 표시 없는 옛 파일은 홈과 옛 설명 줄의 scale(없으면 1)로 읽는다."""
    ref, scale = resolve_mapping("candidate", "grip")
    got = read_pair_marker(f"; point grip\n{pair_marker(ref, scale)}\nG90\n", "grip")
    assert close(got[0], ref, 1e-6) and abs(got[1] - scale) < 1e-12
    assert read_pair_marker("; F = x축 180°, scale 0.8, orientation absolute\n; point grip\n", "grip") == \
        (MIROBOT_HOME_GRIP_MM, 0.8)
    assert read_pair_marker("; point flange\nG90\n", "flange") == (MIROBOT_HOME_MM, 1.0)
    assert resolve_mapping("home", "flange") == (mirobot_home_mm("flange"), 1.0)
    try:
        resolve_mapping("candidate", "flange")  # 후보는 파지점 기준으로 정한 값이다
    except ValueError:
        pass
    else:
        raise AssertionError("flange 에 candidate 를 허용하면 안 된다")
    assert MAPPINGS["home"] == (None, 1.0)


if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            ran += 1
    print(f"\n{ran}개 통과")
