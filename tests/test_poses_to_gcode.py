"""tools/poses_to_gcode.py — 손 좌표 JSONL → Mirobot G-code. 표준 라이브러리만으로 돈다 (10/8 분리)."""

from __future__ import annotations

import argparse
import json

import pytest

from common.workspace import MIROBOT_HOME_MM
from tools.poses_to_gcode import add_arguments, convert, read_poses

# LIBERO 빈 탁상 Panda 시작 위치 (docs/W5/TABLE_ALIGNMENT.md 2절). 자세는 공구 축이 정확히 아래 —
# Mirobot A0 B0 C0 를 LIBERO 규약으로 옮긴 F (x축 180°, wxyz (0,1,0,0)). 실제 시작은 3.3° 기울어 있어
# 파지점끼리 맞추면 플랜지가 수평으로 몇 mm 비켜난다 — 여기서는 그 효과를 빼고 짝과 배율만 본다
START_POS = [-0.2084646605658239, 0.0, 1.1732794757296405]
START_QUAT_XYZW = [1.0, 0.0, 0.0, 0.0]


def options(*argv):
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    return parser.parse_args(list(argv))


def poses(steps):
    """시작 자세에서 x 로 1cm 씩 가며 grasp 에서 그리퍼를 닫는 짧은 기록."""
    meta = {"format": "panda-poses/1", "start_eef_pos": START_POS, "start_eef_quat_xyzw": START_QUAT_XYZW}
    rows = []
    for k in range(1, steps + 1):
        pos = [START_POS[0] + 0.01 * k, START_POS[1], START_POS[2]]
        rows.append({"step": k, "action": [0.0] * 6 + [1.0 if k > steps // 2 else -1.0],
                     "eef_pos": pos, "eef_quat_xyzw": START_QUAT_XYZW})
    return meta, rows


def g0(lines):
    return [line for line in lines if line.startswith("G0")]


def test_start_pose_maps_to_the_mirobot_pair_point():
    meta, rows = poses(1)
    rows[0]["eef_pos"] = START_POS
    lines, out_rows, info = convert(meta, rows, options(), "test", "test")
    x, y, z = out_rows[0]["mirobot_xyz_mm"]
    assert (x, y, z) == pytest.approx(MIROBOT_HOME_MM, abs=0.02)
    assert info["roundtrip_mm"] < 0.02


def test_scale_shrinks_the_displacement():
    meta, rows = poses(4)
    _, full, _ = convert(meta, rows, options(), "test", "test")
    _, half, _ = convert(meta, rows, options("--scale", "0.5"), "test", "test")
    dx_full = full[-1]["mirobot_xyz_mm"][0] - MIROBOT_HOME_MM[0]
    dx_half = half[-1]["mirobot_xyz_mm"][0] - MIROBOT_HOME_MM[0]
    assert dx_full == pytest.approx(40.0, abs=0.5)
    assert dx_half == pytest.approx(dx_full / 2, abs=0.05)


def test_gripper_lines_go_before_the_step_where_the_sign_changes():
    meta, rows = poses(6)
    lines, _, info = convert(meta, rows, options("--gripper"), "test", "test")
    assert info["gripper_at"] == {1: "M4 S40", 4: "M4 S60"}
    body = [line for line in lines if not line.startswith(";")]
    close = body.index("M4 S60")
    assert body[close + 1] == g0(lines)[3]     # 닫기 다음 줄이 스텝 4 의 G0
    assert any("--auto" in line for line in lines if line.startswith(";"))


def test_every_keeps_gripper_steps_the_step_before_and_the_last_step():
    meta, rows = poses(10)
    lines, _, info = convert(meta, rows, options("--gripper", "--every", "4"), "test", "test")
    kept = [r["step"] for r in info["kept"]]
    assert kept == [1, 4, 5, 6, 8, 10]         # 1·6 그리퍼, 5 그리퍼 바로 앞, 4·8 every, 10 마지막
    assert len(g0(lines)) == len(kept)


def test_gripper_closes_after_reaching_the_pose_before_the_change():
    # 10/11: --every 5 에서 M4 앞 G0 가 잡는 높이보다 한참 위였다. M4 바로 앞 G0 는 바뀌기 직전 스텝이어야 한다
    meta, rows = poses(22)                      # 그리퍼는 스텝 12 에서 닫힘 — 바로 앞 11 은 5 의 배수가 아니다
    lines, out_rows, _ = convert(meta, rows, options("--gripper", "--every", "5"), "test", "test")
    body = [line for line in lines if not line.startswith(";")]
    close = body.index("M4 S60")
    step11 = next(r for r in out_rows if r["step"] == 11)
    x, y, z = step11["mirobot_xyz_mm"]
    assert body[close - 1].startswith(f"G0 X{x:.2f} Y{y:.2f} Z{z:.2f}")


def test_no_gripper_lines_without_the_flag():
    meta, rows = poses(6)
    lines, _, _ = convert(meta, rows, options(), "test", "test")
    assert not any(line.startswith("M4") for line in lines)


def test_read_poses_needs_the_start_pose(tmp_path):
    path = tmp_path / "old.jsonl"
    path.write_text(json.dumps({"meta": {"task": "red"}}) + "\n"
                    + json.dumps({"step": 1, "action": [0] * 7, "eef_pos": START_POS,
                                  "eef_quat_xyzw": START_QUAT_XYZW}) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="start_eef_pos"):
        read_poses(path)


def test_read_poses_skips_result_lines(tmp_path):
    meta, rows = poses(3)
    path = tmp_path / "pickup.jsonl"
    path.write_text("\n".join([json.dumps({"meta": meta})] + [json.dumps(r) for r in rows]
                              + [json.dumps({"result": {"steps": 3}})]) + "\n", encoding="utf-8")
    read_meta, read_rows = read_poses(path)
    assert read_meta["format"] == "panda-poses/1"
    assert [r["step"] for r in read_rows] == [1, 2, 3]
