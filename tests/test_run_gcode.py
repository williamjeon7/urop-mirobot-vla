"""`tools/run_gcode.py` 의 Z 하한 검사 확인 테스트.

    python -m tests.test_run_gcode
"""

from __future__ import annotations

import math

from tools.run_gcode import Z_FLOOR_MM, Z_WARN_MM, closest_passes, low_lines, stream_blocker, z_of


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



def lerp(a, b, u):
    return [x + (y - x) * u for x, y in zip(a, b)]


def test_closest_constant_orientation_repeated():
    """10/5 1157줄과 같은 꼴 — 자세가 거의 일정하고 같은 고리를 4번 돈다, 버퍼는 비어 있다(보내고 0.1초 뒤 지나간다).
    옛 화면 표는 자세 최근접을 끝까지 찾아 탐색이 실행 끝으로 밀렸다 (중앙 23 · 최대 77mm)."""
    ring = [[200 + 30 * math.cos(2 * math.pi * i / 50), 30 * math.sin(2 * math.pi * i / 50), 200, 0, 3, 0]
            for i in range(50)]
    path, dt, lag = ring * 4, 0.117, 0.1
    sent = [{"label": f"s{k}", "commanded": c, "t_s": k * dt} for k, c in enumerate(path)]

    def at(t):  # 그 시각 로봇 자세 — 보낸 뒤 lag 초에 그 waypoint 를 지난다
        u = min(max((t - lag) / dt, 0), len(path) - 1)
        k = min(int(u), len(path) - 2)
        return lerp(path[k], path[k + 1], u - k)

    samples = []
    for j in range(int((len(path) * dt + 1) / 0.0885)):
        cart = at(j * 0.0885)
        cart[4] += 0.01 * math.sin(j)  # 자세는 잡음만
        samples.append({"t_s": j * 0.0885, "cart": cart})
    rows = closest_passes(sent, samples)
    pos = sorted(r["pos_mm"] for r in rows)
    assert pos[len(pos) // 2] < 1.0 and pos[-1] < 2.0, (pos[len(pos) // 2], pos[-1])
    assert all(abs(r["pos_t"] - (r["t_s"] + lag)) < 0.1 for r in rows[1:])  # 제 회차에서 찾았다 (첫 줄은 이미 그 자리에 있다)


def test_closest_buffer_lag_repeated_pose():
    """9/21 61줄과 같은 꼴 — 버퍼가 차서 실행이 보내기보다 몇 초 늦고, 같은 자세(홈)가 되풀이된다.
    "보낸 뒤 몇 초" 로 묶으면 뒤의 B20 · C20 을 못 찾고 앞의 홈을 집는다."""
    home = [198.67, 0, 230.72, 0, 0, 0]
    poses = [home, home[:3] + [20, 0, 0], home, home[:3] + [0, 20, 0], home, home[:3] + [0, 0, 20], home]
    sent = [{"label": f"w{k}", "commanded": c, "t_s": 0.02 * k} for k, c in enumerate(poses)]  # 다 금방 보낸다

    def at(t):  # waypoint k 에 t = k + 1 초에 닿는다 (한 동작 1초, 줄 순서대로)
        u = min(max(t - 1.0, 0), len(poses) - 1)
        k = min(int(u), len(poses) - 2)
        return lerp(poses[k], poses[k + 1], u - k)

    samples = [{"t_s": j * 0.05, "cart": at(j * 0.05)} for j in range(int(9 / 0.05))]
    rows = closest_passes(sent, samples)
    assert all(r["rot_deg"] < 0.6 for r in rows), [round(r["rot_deg"], 2) for r in rows]
    times = [r["rot_t"] for r in rows]
    assert times == sorted(times)
    assert all(abs(rows[k]["rot_t"] - (k + 1)) < 0.06 for k in (1, 3, 5))  # 돈 자세는 제때 찾았다


def test_closest_after_last_sample():
    """마지막 샘플 뒤에 보낸 줄은 기록 없음 — 에러로 일찍 멈춘 경우."""
    sent = [{"label": "a", "commanded": [200, 0, 200, 0, 0, 0], "t_s": 0.0},
            {"label": "b", "commanded": [210, 0, 200, 0, 0, 0], "t_s": 5.0}]
    rows = closest_passes(sent, [{"t_s": 0.1, "cart": [200, 0, 200, 0, 0, 0]}])
    assert rows[0]["pos_mm"] == 0.0 and "pos_mm" not in rows[1]
    assert closest_passes(sent, []) == [{"label": "a", "t_s": 0.0}, {"label": "b", "t_s": 5.0}]


if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            ran += 1
    print(f"\n{ran}개 통과")



# --stream 은 설정 줄을 먼저 보내므로 이동 사이 M4(그리퍼)가 있으면 거부한다 (10/8)
def test_settings_before_moves_do_not_block_stream():
    entries = [("", "G90"), ("", "M20"), ("", "M4 S40"), ("a", "G0 X1 Y2 Z90 A0 B0 C0")]
    assert stream_blocker(entries) is None


def test_gripper_between_moves_blocks_stream():
    entries = [("", "G90"), ("a", "G0 X1 Y2 Z90 A0 B0 C0"), ("g", "M4 S60"),
               ("b", "G0 X1 Y2 Z120 A0 B0 C0")]
    assert stream_blocker(entries) == "M4 S60"
