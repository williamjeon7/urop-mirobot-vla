"""`common/proprio.py` 확인 테스트.

    python -m tests.test_proprio

왕복 — Panda 손 자세 → Mirobot G0 (`tools/poses_to_gcode.py` 와 같은 계산, 소수 둘째 자리 반올림) → `mirobot_to_libero_pose`.
위치는 W6 에서 이미 확인했고(최대 0.013 mm), 여기서는 **자세(쿼터니언)와 부호**까지 본다.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from common.proprio import (
    FINGER_HOLD_M,
    FINGER_OPEN_M,
    align_sign,
    fingers,
    mirobot_to_libero_pose,
    robot_states,
    settings_from_gcode,
)
from common.rotation import (
    FRAME_F,
    libero_to_mirobot_quat,
    quat_from_axis_deg,
    quat_mul,
    quat_to_euler_xyz_deg,
    quat_xyzw_to_wxyz,
)
from common.workspace import grip_to_flange, libero_to_mirobot_flange_mm, resolve_mapping

REPO = Path(__file__).resolve().parents[1]
POSES = REPO / "docs" / "W6" / "poses" / "pickup-red-s2.jsonl"
GCODE = REPO / "trajectories" / "2026_10_11-w6-pickup-red-s2-e5.gcode"  # 출처가 위 POSES 인 파일

# W6 시뮬 Panda 시작 자세 — pickup-red-s2 meta 의 start_eef_* 와 같은 값 (파지점, xyzw)
START_GRIP_M = (-0.2084646605658239, 0.0, 1.1732794757296405)
START_Q = quat_mul(quat_from_axis_deg("y", 3.28), FRAME_F)  # 3.28° 기운 top-down


def angle_deg(a, b) -> float:
    """두 쿼터니언 사이 회전각 (부호와 무관)."""
    d = min(1.0, abs(sum(x * y for x, y in zip(a, b))))
    return math.degrees(2 * math.acos(d))


def to_gcode_pose(grip_m, q, ref_flange, ref_q, settings):
    """poses_to_gcode.convert 와 같은 계산 → G-code 에 적히는 반올림 값."""
    q_m = libero_to_mirobot_quat(q)
    xyz = libero_to_mirobot_flange_mm(grip_to_flange(grip_m, q), q, q_m, ref_flange, ref_q, settings["point"],
                                      settings["scale"], settings["ref_mirobot_mm"], settings["tool_mm"])
    return [round(v, 2) for v in xyz], [round(v, 2) for v in quat_to_euler_xyz_deg(q_m)]


def test_settings_from_gcode():
    s = settings_from_gcode(GCODE.read_text(encoding="utf-8"))
    assert s["point"] == "grip" and s["orientation"] == "absolute"
    assert s["ref_mirobot_mm"] == (213.67, 0.0, 175.72) and abs(s["scale"] - 0.663) < 1e-12
    assert s["tool_mm"] == (15.0, 0.0, -55.0)


def test_round_trip_synthetic():
    """위치 ±10 cm, 기울기 ±10°, 손목 회전 ±40° — 반올림만큼만 어긋나야 한다."""
    ref_mirobot, _ = resolve_mapping("home", "grip")
    settings = {"point": "grip", "tool_mm": (15.0, 0.0, -55.0), "ref_mirobot_mm": ref_mirobot,
                "scale": 0.663, "orientation": "absolute"}
    ref_flange = grip_to_flange(START_GRIP_M, START_Q)
    worst_mm, worst_deg = 0.0, 0.0
    for dx, dy, dz in ((0, 0, 0), (0.1, -0.05, -0.08), (-0.06, 0.1, 0.02)):
        for axis, deg in (("x", 0), ("x", 10), ("y", -10), ("z", 40), ("z", -40)):
            q = quat_mul(quat_from_axis_deg(axis, deg), START_Q)
            p = (START_GRIP_M[0] + dx, START_GRIP_M[1] + dy, START_GRIP_M[2] + dz)
            xyz, abc = to_gcode_pose(p, q, ref_flange, START_Q, settings)
            back_p, back_q = mirobot_to_libero_pose(xyz, abc, ref_flange, START_Q, settings)
            worst_mm = max(worst_mm, math.dist(back_p, p) * 1000 * settings["scale"])
            worst_deg = max(worst_deg, angle_deg(back_q, q))
            assert sum(a * b for a, b in zip(back_q, q)) > 0, "부호가 기준과 반대"
    assert worst_mm < 0.02 and worst_deg < 0.02, (worst_mm, worst_deg)


def test_round_trip_w6_files():
    """실제 W6 파일 쌍 — 손 좌표 기록과 그것으로 만든 G-code. G0 마다 되돌려 원래 자세와 댄다."""
    rows = [json.loads(line) for line in POSES.read_text(encoding="utf-8").splitlines()]
    meta, by_step = rows[0]["meta"], {r["step"]: r for r in rows[1:] if "step" in r}
    ref_q = quat_xyzw_to_wxyz(tuple(meta["start_eef_quat_xyzw"]))
    ref_flange = grip_to_flange(meta["start_eef_pos"], ref_q)
    text = GCODE.read_text(encoding="utf-8")
    settings = settings_from_gcode(text)
    worst_mm, worst_deg, n, step = 0.0, 0.0, 0, None
    for line in text.splitlines():
        label = re.match(r";\s*c\d+s(\d+)", line)
        if label:
            step = int(label.group(1))
            continue
        g0 = re.match(r"G0 X(\S+) Y(\S+) Z(\S+) A(\S+) B(\S+) C(\S+)", line)
        if g0 and step is not None:
            v = [float(x) for x in g0.groups()]
            back_p, back_q = mirobot_to_libero_pose(v[:3], v[3:], ref_flange, ref_q, settings)
            row = by_step[step]
            q = quat_xyzw_to_wxyz(tuple(row["eef_quat_xyzw"]))
            worst_mm = max(worst_mm, math.dist(back_p, row["eef_pos"]) * 1000 * settings["scale"])
            worst_deg = max(worst_deg, angle_deg(back_q, q))
            assert sum(a * b for a, b in zip(back_q, q)) > 0, f"step {step}: 부호가 원래와 반대"
            n, step = n + 1, None
    print(f"    G0 {n}줄 — 위치 최대 {worst_mm:.4f} mm (Mirobot 기준), 자세 최대 {worst_deg:.4f}°, 부호 모두 같음")
    assert n > 20 and worst_mm < 0.02 and worst_deg < 0.02, (n, worst_mm, worst_deg)


def test_align_sign():
    q = (0.01, 0.99, 0.0, -0.1)
    assert align_sign(q, FRAME_F) == q
    assert align_sign(tuple(-v for v in q), FRAME_F) == q


def test_fingers_b_prime():
    """0 = 열림, 1 = 블록을 잡음. 범위 밖은 자른다. 빈손으로 끝까지 닫은 값(0)은 나오지 않는다."""
    assert fingers(0.0) == (FINGER_OPEN_M, -FINGER_OPEN_M)
    assert fingers(1.0) == (FINGER_HOLD_M, -FINGER_HOLD_M)
    assert fingers(2.0) == fingers(1.0) and fingers(-1.0) == fingers(0.0)
    left, right = fingers(0.5)
    assert FINGER_HOLD_M < left < FINGER_OPEN_M and right == -left


def test_robot_states_order():
    """손가락 2 + 위치 3 + 쿼터니언 xyzw 4. top-down(x 축 180°) 은 xyzw 로 (1, 0, 0, 0)."""
    s = robot_states(fingers(0.0), (0.1, 0.2, 0.3), FRAME_F)
    assert len(s) == 9 and s[:5] == [FINGER_OPEN_M, -FINGER_OPEN_M, 0.1, 0.2, 0.3]
    assert all(abs(a - b) < 1e-12 for a, b in zip(s[5:], (1.0, 0.0, 0.0, 0.0)))


if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            ran += 1
    print(f"\n{ran}개 통과")
