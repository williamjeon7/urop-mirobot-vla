#!/usr/bin/env python3
"""W3 ④ LIBERO → Mirobot — 롤아웃 기록의 waypoint 를 Mirobot G-code 로 바꾼다. (numpy 없이 돈다)

    python -m tools.libero_to_mirobot_gcode                               # data/compound/ 의 최신 기록
    python -m tools.libero_to_mirobot_gcode --log data/compound/<파일>.jsonl --scale 0.8

변환 (docs/W3/LIBERO_AXES.md 4절)
  자세  q_mirobot = q_libero ⊗ F⁻¹, F = x축 180° (9/17 확정) → extrinsic XYZ 오일러(도) → G0 의 A B C
  위치  플랜지 ↔ 플랜지. Panda 시작 플랜지 ↔ Mirobot 홈을 짝지어 변위만 옮긴다 (common/workspace.py)

--orientation
  absolute  기록된 자세를 그대로 옮긴다. Panda 시작이 3.3° 기울어 있어 Mirobot 시작이 B≈+3.3 이 된다
  relative  시작 자세로부터의 회전만 옮긴다. Mirobot 시작이 (0,0,0) — Panda 시작의 기울기를 지운다

남는 것 — 기록 옆에 <이름>--mirobot.gcode. 실행기는 ';' 줄을 건너뛰고 G0 마다 정지를 확인한 뒤 다음 줄로 가야 한다.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path

from common.rotation import (
    euler_xyz_deg_to_quat,
    libero_to_mirobot_quat,
    mirobot_to_libero_quat,
    quat_conj,
    quat_mul,
    quat_to_euler_xyz_deg,
    quat_xyzw_to_wxyz,
)
from common.workspace import MIROBOT_HOME_MM, libero_to_mirobot_xyz_mm, mirobot_to_libero_xyz_m

REACH_WARN_MM = 280.0  # 수평 거리. Mirobot 도달 약 315mm (9/14 미팅 메모) — 여유를 둔다
ANGLE_WARN_DEG = 30.0


def angle_deg(q1, q2) -> float:
    r = quat_mul(quat_conj(q1), q2)
    return math.degrees(2 * math.atan2(math.sqrt(r[1] ** 2 + r[2] ** 2 + r[3] ** 2), abs(r[0])))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", type=Path, help="롤아웃 jsonl. 없으면 data/compound/ 의 최신")
    parser.add_argument("--scale", type=float, default=1.0, help="위치 변위에만 곱한다")
    parser.add_argument("--orientation", choices=("absolute", "relative"), default="absolute")
    args = parser.parse_args()

    log = args.log or Path(sorted(glob.glob("data/compound/*.jsonl"))[-1])
    rows = [json.loads(line) for line in log.open()]
    meta, steps = rows[0]["meta"], rows[1:]
    wps = [r for r in steps if r.get("waypoint")]
    ref_pos = wps[0]["flange_pos"]
    q_ref_libero = quat_xyzw_to_wxyz(tuple(wps[0]["flange_quat_xyzw"]))

    def to_mirobot_quat(q_libero):
        if args.orientation == "absolute":
            return libero_to_mirobot_quat(q_libero)
        return quat_mul(q_libero, quat_conj(q_ref_libero))  # 시작으로부터의 월드 회전을 Mirobot 항등에 얹는다

    def back_to_libero_quat(q_mirobot):
        if args.orientation == "absolute":
            return mirobot_to_libero_quat(q_mirobot)
        return quat_mul(q_mirobot, q_ref_libero)

    lines = [f"; LIBERO → Mirobot  {log}",
             f"; task {meta['task']}  segments {[s[0] for s in meta['segments']]}",
             f"; F = x축 180°, 플랜지 ↔ 플랜지, Panda 시작 ↔ Mirobot 홈 {MIROBOT_HOME_MM}, "
             f"scale {args.scale}, orientation {args.orientation}",
             "G90", "M20"]
    print(f"{log}  —  waypoint {len(wps)}개, scale {args.scale}, orientation {args.orientation}\n")
    print(f"{'waypoint':12} | {'X':>8} {'Y':>8} {'Z':>8} mm | {'A(Rx)':>7} {'B(Ry)':>7} {'C(Rz)':>7} ° | {'수평거리':>6} | 검산 위치·자세")
    worst_pos = worst_rot = 0.0
    warnings = []
    for w in wps:
        q_libero = quat_xyzw_to_wxyz(tuple(w["flange_quat_xyzw"]))
        xyz = libero_to_mirobot_xyz_mm(w["flange_pos"], ref_pos, scale=args.scale)
        abc = quat_to_euler_xyz_deg(to_mirobot_quat(q_libero))
        xyz_r, abc_r = tuple(round(v, 2) for v in xyz), tuple(round(v, 2) for v in abc)  # 파일에 쓰는 값

        # 검산 — 파일에 쓴 (반올림된) 값으로 되돌려 원래 기록과 비교
        p_back = mirobot_to_libero_xyz_m(xyz_r, ref_pos, scale=args.scale)
        e_pos = math.dist(p_back, w["flange_pos"]) * 1000 * args.scale
        e_rot = angle_deg(back_to_libero_quat(euler_xyz_deg_to_quat(*abc_r)), q_libero)
        worst_pos, worst_rot = max(worst_pos, e_pos), max(worst_rot, e_rot)

        reach = math.hypot(xyz_r[0], xyz_r[1])
        if reach > REACH_WARN_MM:
            warnings.append(f"{w['waypoint']}: 수평거리 {reach:.1f}mm > {REACH_WARN_MM}")
        if max(abs(v) for v in abc_r) > ANGLE_WARN_DEG:
            warnings.append(f"{w['waypoint']}: 각도 {abc_r} 에 {ANGLE_WARN_DEG}° 초과")

        print(f"{w['waypoint']:12} | {xyz_r[0]:8.2f} {xyz_r[1]:8.2f} {xyz_r[2]:8.2f}    | "
              f"{abc_r[0]:7.2f} {abc_r[1]:7.2f} {abc_r[2]:7.2f}   | {reach:6.1f} | {e_pos:.3f}mm {e_rot:.3f}°")
        lines += [f"; {w['waypoint']}  (step {w['step']}, {w['phase']})",
                  f"G0 X{xyz_r[0]:.2f} Y{xyz_r[1]:.2f} Z{xyz_r[2]:.2f} A{abc_r[0]:.2f} B{abc_r[1]:.2f} C{abc_r[2]:.2f}"]

    out = log.with_name(f"{log.stem}--mirobot-{args.orientation}.gcode")
    out.write_text("\n".join(lines) + "\n")
    print(f"\n검산 최대 오차 — 위치 {worst_pos:.3f}mm, 자세 {worst_rot:.3f}°  (파일에 소수 둘째 자리로 쓰면서 생기는 반올림)")
    print("경고 없음" if not warnings else "경고\n  " + "\n  ".join(warnings))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
