"""`tools/run_gcode.py` 의 Z 하한 검사 확인 테스트.

    python -m tests.test_run_gcode
"""

from __future__ import annotations

from tools.run_gcode import Z_FLOOR_MM, Z_WARN_MM, low_lines, z_of


def entries(*commands: str) -> list[tuple[str, str]]:
    return [(f"l{i}", c) for i, c in enumerate(commands)]


def test_z_of_reads_moves_only():
    """G0/G00/G1/G01 의 Z 만 읽는다. 설정 줄과 Z 없는 이동은 None."""
    assert z_of("G0 X200.00 Y0.00 Z65.50 A0.00 B0.00 C0.00") == 65.5
    assert z_of("g00 z-3") == -3.0
    assert z_of("G1 X10 Z 80") == 80.0
    assert z_of("G01 Z70") == 70.0
    assert z_of("G0 X200 Y0") is None
    assert z_of("G90") is None and z_of("M20") is None and z_of("M4 S30") is None
    assert z_of("G04 P1") is None  # 대기 명령은 이동이 아니다


def test_partial_move_is_checked():
    """여섯 축이 다 없는 `G0 Z50` 은 `pose_of` 가 설정 줄로 치지만, 하한 검사에서는 빠지면 안 된다."""
    got = low_lines(entries("G90", "G0 X200 Y0 Z100 A0 B0 C0", "G0 Z50", "G0 X200 Y0 Z70 A0 B0 C0"), Z_FLOOR_MM)
    assert [(w, z) for w, _, z in got] == [("'G0 Z50'", 50.0)]


def test_floor_and_warn_split():
    """66 아래는 막고, 66~71 은 경고 — 경계값 66 은 막지 않는다."""
    cmds = entries(*(f"G0 X200 Y0 Z{z} A0 B0 C0" for z in (230.72, 71, 70.9, 66, 65.9, 60.713)))
    blocked = [z for _, _, z in low_lines(cmds, Z_FLOOR_MM)]
    warned = [z for _, _, z in low_lines(cmds, Z_WARN_MM) if z >= Z_FLOOR_MM]
    assert blocked == [65.9, 60.713]
    assert warned == [70.9, 66.0]


if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            ran += 1
    print(f"\n{ran}개 통과")
