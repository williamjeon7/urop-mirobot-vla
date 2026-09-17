"""`common/workspace.py` 확인 테스트.

    python -m tests.test_workspace
"""

from __future__ import annotations

from common.workspace import MIROBOT_HOME_MM, libero_to_mirobot_xyz_mm, mirobot_to_libero_xyz_m

# 9/17 libero_90[7] 안정 후 플랜지 위치 (m, 월드) — 값 자체보다 "기준점" 역할이다
PANDA_START_FLANGE_M = (-0.2185, 0.0135, 1.2735)


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


if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            ran += 1
    print(f"\n{ran}개 통과")
