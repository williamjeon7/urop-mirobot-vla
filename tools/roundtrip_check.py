#!/usr/bin/env python3
"""W3 ④ 왕복 검증 — Mirobot 이 실제로 간 자세를 LIBERO 로 되돌려 원본과 대 본다. (numpy 없이 돈다)

    # 로봇 노트북 — 실행 기록에서 waypoint 별 `?` 보고값을 뽑는다
    python -m tools.roundtrip_check extract --run-log data/probe/20260920_105128.jsonl \
        --gcode trajectories/2026_09_17-compound-relative.gcode \
        --out trajectories/2026_09_20-compound-measured.jsonl

    # 서버 — 되돌려 원본 롤아웃과 비교한다
    python -m tools.roundtrip_check compare --measured trajectories/2026_09_20-compound-measured.jsonl \
        --rollout data/compound/2026_09_17-10_44_39.jsonl

왕복  LIBERO 원본 ──변환──▶ Mirobot G0 ──실물──▶ `?` 보고값 ──역변환──▶ LIBERO
  잡는 것    실물 추종 오차, 위치 변환(원점·단위·스케일), 플랜지 ↔ 파지점 오프셋, 파일 반올림
  못 잡는 것 프레임 회전 `F` — 나갈 때 곱하고 들어올 때 나눠 **상쇄된다**. `F` 는 Mirobot 에서 출발하는
             축별 시험으로 따로 잡는다 (docs/W3/CHECKLIST.md 5-1, ROTATION.md 7절 "왕복만으로는 못 잡는다")

`extract` 는 `--out` 옆에 같은 이름의 `.gcode` 도 쓴다. **보고값 그대로**의 G-code 라
`python -m tools.libero_follow --gcode <그 파일>` 로 영상까지 이어갈 수 있다 (absolute 파일일 때).

읽는 기록 두 가지 — `tools/run_gcode.py` 의 `waypoint` 줄, 또는 `tools/probe_mirobot.py` 로 손으로 보낸
`send` + `raw` 짝. 어느 쪽이든 G-code 의 좌표와 맞춰 waypoint 이름을 붙인다.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from common.rotation import (
    euler_xyz_deg_to_quat,
    mirobot_to_libero_quat,
    quat_conj,
    quat_mul,
    quat_xyzw_to_wxyz,
)
from common.workspace import flange_to_grip, mirobot_to_libero_xyz_m
from tools.probe_mirobot import fields, find_field, is_status, state_of
from tools.run_gcode import parse_file, pose_of

HEADER_RE = re.compile(r"scale\s+([0-9.]+),\s*orientation\s+(\w+)")


def angle_deg(q1, q2) -> float:
    """두 자세 사이의 회전각(도). `libero_to_mirobot_gcode.py` 와 같은 식."""
    r = quat_mul(quat_conj(q1), q2)
    return math.degrees(2 * math.atan2(math.sqrt(r[1] ** 2 + r[2] ** 2 + r[3] ** 2), abs(r[0])))


def key_of(pose) -> tuple:
    """G-code 좌표를 기록과 맞추는 열쇠. 파일이 소수 둘째 자리라 그 자리에서 비교한다."""
    return tuple(round(v, 2) for v in pose)


def read_gcode(path: Path) -> tuple[list[tuple[str, list[float]]], float, str]:
    """(이름, [X Y Z A B C]) 목록과 머리말의 scale·orientation."""
    wps = [(label, pose) for label, command in parse_file(path)
           if (pose := pose_of(command)) is not None]
    scale, orientation = 1.0, "absolute"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(";") and (m := HEADER_RE.search(line)):
            scale, orientation = float(m.group(1)), m.group(2)
    return wps, scale, orientation


def reported_by_pose(log_path: Path) -> dict[tuple, dict]:
    """실행 기록 → {명령 좌표: {state, xyz, rxryrz, angle}}. `waypoint` 줄이 없으면 send+raw 짝으로."""
    rows = [json.loads(line) for line in log_path.open(encoding="utf-8")]
    out: dict[tuple, dict] = {}

    for row in rows:  # tools/run_gcode.py 가 남긴 줄
        if row.get("kind") == "waypoint" and row.get("reported") and len(row["reported"]) >= 6:
            out[key_of(row["commanded"])] = {"state": "Idle", "xyz_mm": row["reported"][:3],
                                             "rxryrz_deg": row["reported"][3:6], "angle": None}
    if out:
        return out

    pending = None  # tools/probe_mirobot.py 로 손으로 보낸 경우 — send 다음의 첫 상태 줄이 그 명령의 결과다
    for row in rows:
        kind, cmd = row.get("kind"), row.get("cmd", "")
        if kind == "send" and cmd.upper().startswith("G0"):
            pending = pose_of(cmd)
        elif kind in ("raw", "send") and pending is not None:
            status = next((line for _, line in (row.get("lines") or [])
                           if isinstance(line, str) and is_status(line)), None)
            if status is None:
                continue
            parsed = fields(status)
            cart = find_field(parsed, "Cartesian")
            if cart and len(cart) >= 6:
                out[key_of(pending)] = {"state": state_of(status), "xyz_mm": cart[:3],
                                        "rxryrz_deg": cart[3:6], "angle": find_field(parsed, "Angle")}
                pending = None
    return out


def cmd_extract(args) -> None:
    wps, scale, orientation = read_gcode(args.gcode)
    reported = reported_by_pose(args.run_log)
    missing = [label for label, pose in wps if key_of(pose) not in reported]
    if missing:
        raise SystemExit(f"기록에서 못 찾은 waypoint: {missing}\n  {args.run_log} 에 그 좌표의 G0 와 상태 줄이 있는지 볼 것")

    rows = []
    print(f"{args.gcode}  —  waypoint {len(wps)}개, scale {scale}, orientation {orientation}")
    print(f"\n{'waypoint':12} | {'명령 X Y Z':>26} | {'보고 X Y Z':>26} | {'Δ위치':>8} | {'Δ자세 (Rx Ry Rz)':>24}")
    worst_pos = worst_rot = 0.0
    for label, pose in wps:
        got = reported[key_of(pose)]
        d_pos = math.dist(got["xyz_mm"], pose[:3])
        d_rot = [r - c for r, c in zip(got["rxryrz_deg"], pose[3:6])]
        worst_pos, worst_rot = max(worst_pos, d_pos), max(worst_rot, max(abs(v) for v in d_rot))
        rows.append({"waypoint": label, "state": got["state"], "commanded": pose,
                     "reported_xyz_mm": got["xyz_mm"], "reported_rxryrz_deg": got["rxryrz_deg"],
                     "reported_angle_abcdxyz": got["angle"]})
        print(f"{label:12} | {pose[0]:8.2f} {pose[1]:8.2f} {pose[2]:8.2f} | "
              f"{got['xyz_mm'][0]:8.2f} {got['xyz_mm'][1]:8.2f} {got['xyz_mm'][2]:8.2f} | "
              f"{d_pos:7.3f}mm | {d_rot[0]:+7.3f} {d_rot[1]:+7.3f} {d_rot[2]:+7.3f}")
    print(f"\n실물 추종 오차 — 위치 최대 {worst_pos:.3f}mm, 자세 최대 {worst_rot:.3f}°")

    meta = {"meta": {"run_log": args.run_log.as_posix(), "gcode": args.gcode.as_posix(),
                     "scale": scale, "orientation": orientation, "waypoints": len(rows),
                     "note": "reported_* 는 Mirobot `?` 보고값 (플랜지 mm, extrinsic XYZ 도)"}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"saved {args.out}")

    gcode_out = args.out.with_suffix(".gcode")
    lines = [f"; Mirobot 이 실제로 간 자세 (`?` 보고값). 원본 {args.gcode.as_posix()}, 기록 {args.run_log.as_posix()}",
             f"; scale {scale}, orientation {orientation}", "G90", "M20"]
    for row in rows:
        x, y, z = row["reported_xyz_mm"]
        a, b, c = row["reported_rxryrz_deg"]
        lines += [f"; {row['waypoint']}", f"G0 X{x:.2f} Y{y:.2f} Z{z:.2f} A{a:.2f} B{b:.2f} C{c:.2f}"]
    gcode_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"saved {gcode_out}")


def cmd_compare(args) -> None:
    measured = [json.loads(line) for line in args.measured.open(encoding="utf-8")]
    meta, rows = measured[0]["meta"], measured[1:]
    scale = args.scale if args.scale is not None else meta.get("scale", 1.0)
    orientation = args.orientation or meta.get("orientation", "absolute")

    origin = [json.loads(line) for line in args.rollout.open(encoding="utf-8")][1:]
    wps = {r["waypoint"]: r for r in origin if r.get("waypoint")}
    ref = next(r for r in origin if r.get("waypoint"))  # 첫 waypoint = 기준점 (변환할 때와 같다)
    ref_pos, q_ref = ref["flange_pos"], quat_xyzw_to_wxyz(tuple(ref["flange_quat_xyzw"]))

    def back_to_libero_quat(q_mirobot):
        """G-code 를 만들 때 쓴 변환의 역 (`tools/libero_to_mirobot_gcode.py`)."""
        return mirobot_to_libero_quat(q_mirobot) if orientation == "absolute" else quat_mul(q_mirobot, q_ref)

    print(f"{args.measured}  ←→  {args.rollout}")
    print(f"기준점 {ref['waypoint']} (step {ref['step']}), scale {scale}, orientation {orientation}\n")
    print(f"{'waypoint':12} | {'Δx':>7} {'Δy':>7} {'Δz':>7} mm | {'거리':>7} | {'자세':>7} | {'파지점':>7}")
    worst = {"pos": 0.0, "rot": 0.0, "grip": 0.0}
    for row in rows:
        origin_row = wps.get(row["waypoint"])
        if origin_row is None:
            print(f"{row['waypoint']:12} | 원본 기록에 없다")
            continue
        q_back = back_to_libero_quat(euler_xyz_deg_to_quat(*row["reported_rxryrz_deg"]))
        p_back = mirobot_to_libero_xyz_m(row["reported_xyz_mm"], ref_pos, scale=scale)
        p_orig = origin_row["flange_pos"]
        q_orig = quat_xyzw_to_wxyz(tuple(origin_row["flange_quat_xyzw"]))

        d = [(b - o) * 1000.0 for b, o in zip(p_back, p_orig)]
        e_pos, e_rot = math.dist(p_back, p_orig) * 1000.0, angle_deg(q_back, q_orig)
        e_grip = math.dist(flange_to_grip(p_back, q_back), flange_to_grip(p_orig, q_orig)) * 1000.0
        worst = {"pos": max(worst["pos"], e_pos), "rot": max(worst["rot"], e_rot),
                 "grip": max(worst["grip"], e_grip)}
        print(f"{row['waypoint']:12} | {d[0]:+7.2f} {d[1]:+7.2f} {d[2]:+7.2f}    | "
              f"{e_pos:6.2f}mm | {e_rot:6.2f}° | {e_grip:6.2f}mm")

    print(f"\n최대 — 플랜지 {worst['pos']:.2f}mm, 자세 {worst['rot']:.2f}°, 파지점 {worst['grip']:.2f}mm")
    print("파지점 오차가 플랜지보다 큰 만큼이 자세 오차가 9.7cm 아래에서 벌어진 몫이다 (docs/W3/CONTROL.md 2절)")
    if orientation == "relative":
        print("orientation relative — 되돌릴 때 기준 자세를 다시 곱하므로 시작 기울기(Panda 3.3°)는 여기서 상쇄된다.")
        print("  같은 파일을 `libero_follow --gcode` 에 그대로 주면 absolute 로 읽혀 그만큼 어긋난다")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("extract", help="실행 기록 + G-code → waypoint 별 보고값 파일")
    p.add_argument("--run-log", type=Path, required=True, help="tools/run_gcode.py 또는 tools/probe_mirobot.py 의 jsonl")
    p.add_argument("--gcode", type=Path, required=True, help="그때 보낸 G-code")
    p.add_argument("--out", type=Path, required=True, help="쓸 파일 (trajectories/ 아래 — 기기 사이를 오간다)")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("compare", help="보고값을 LIBERO 로 되돌려 원본 롤아웃과 비교")
    p.add_argument("--measured", type=Path, required=True, help="extract 가 만든 파일")
    p.add_argument("--rollout", type=Path, required=True, help="원본 롤아웃 jsonl (data/compound/)")
    p.add_argument("--scale", type=float, help="측정 파일의 값을 덮어쓴다")
    p.add_argument("--orientation", choices=("absolute", "relative"), help="측정 파일의 값을 덮어쓴다")
    p.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
