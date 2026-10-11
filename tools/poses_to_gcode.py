#!/usr/bin/env python3
"""W6 ② Panda 손 좌표 → Mirobot G-code. (표준 라이브러리만 — LIBERO 없이 노트북에서도 돈다)

    python -m tools.poses_to_gcode --poses data/pickup/<기록>.jsonl --scale 0.663 --gripper
    python -m tools.poses_to_gcode --poses data/poses/<기록>.jsonl --scale 0.663
    python -m tools.run_gcode <나온 파일> --dry-run        # 도달 범위·Z 하한 경고가 있나

입력은 손 좌표 JSONL 이다 (`docs/W6/DIVISION.md` 3장) — `pickup.py --log` 와 `tools/action_to_poses.py` 가 남긴다.
meta 의 `start_eef_pos` · `start_eef_quat_xyzw` 가 짝의 Panda 쪽(첫 action 직전 손 자세)이고, Mirobot 쪽은 `--mapping` 이다.

    손 좌표 ──▶ 플랜지 ──▶ 짝·배율로 변위 옮김 (common/workspace.py) ──▶ 자세 F (common/rotation.py) ──▶ G0 (절대)

그리퍼 (`--gripper`) — Panda 는 action[6] 의 **부호만** 쓴다 (robosuite `panda_gripper.py` format_action, 스텝마다 0.01 씩).
Mirobot 은 `M4 S<값>` 한 줄이 목표 개폐 위치다. 그래서 부호가 바뀌는 첫 스텝 앞에 `M4` 한 줄을 넣는다.
이 파일은 `run_gcode --auto` 로만 돈다 — `--stream` 은 설정 줄을 먼저 몰아 보내 `M4` 의 순서가 바뀐다.

남는 것
  <--out>                              Mirobot G-code (`; point` · `; pair` 머리말)
  <--log-dir>/<날짜>-<시각>.jsonl        스텝마다 손 좌표·Mirobot 명령 (역변환 검산의 입력)
"""

from __future__ import annotations

import argparse
import json
import math
import time
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
from common.workspace import (
    DEFAULT_MAPPING,
    DEFAULT_POINT,
    MAPPINGS,
    POINTS,
    flange_to_grip,
    grip_to_flange,
    libero_to_mirobot_flange_mm,
    mirobot_to_libero_flange_m,
    pair_marker,
    point_marker,
    resolve_mapping,
)
from tools.run_gcode import ANGLE_WARN_DEG, REACH_WARN_MM, Z_FLOOR_MM, Z_WARN_MM


def read_poses(path: Path) -> tuple[dict, list[dict]]:
    """(meta, 스텝별 행). 행은 `eef_pos` 와 `eef_quat_xyzw` 가 있는 줄만 — `result` 같은 줄은 건너뛴다."""
    meta, rows = {}, []
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        if "meta" in row:
            meta = row["meta"]
        elif "eef_pos" in row and "eef_quat_xyzw" in row:
            rows.append(row)
    missing = [k for k in ("start_eef_pos", "start_eef_quat_xyzw") if k not in meta]
    if missing:
        raise SystemExit(f"{path} meta 에 {missing} 가 없다 — 짝의 Panda 쪽(첫 action 직전 손 자세)이 필요하다. "
                         "pickup.py --log 를 다시 남기거나 tools/action_to_poses.py 로 만든다")
    if not rows:
        raise SystemExit(f"{path} 에 eef_pos · eef_quat_xyzw 가 있는 줄이 없다")
    return meta, rows


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Mirobot 쪽 옵션 — `tools/action_to_gcode.py` 도 그대로 쓴다."""
    parser.add_argument("--out", type=Path, help="쓸 G-code. 기본은 trajectories/<날짜>-translated-<원본이름>.gcode")
    parser.add_argument("--orientation", choices=("absolute", "relative"), default="absolute",
                        help="Mirobot 자세를 월드 기준으로 적을지, 시작 자세로부터의 회전으로 적을지")
    parser.add_argument("--point", choices=POINTS, default=DEFAULT_POINT, help="어느 점끼리 맞추나")
    parser.add_argument("--mapping", choices=sorted(MAPPINGS), default=DEFAULT_MAPPING,
                        help="Mirobot 쪽 짝과 배율 (common/workspace.py MAPPINGS). candidate 는 10/1 후보 — 실물 확인 전")
    parser.add_argument("--scale", type=float, help="배율만 덮어쓴다 (짝은 --mapping 그대로)")
    parser.add_argument("--gripper", action="store_true",
                        help="그리퍼 부호가 바뀌는 스텝 앞에 M4 를 넣는다 (Panda 는 부호만 쓴다). "
                             "이 파일은 run_gcode --auto 로만 — --stream 은 설정 줄을 먼저 몰아 보낸다")
    parser.add_argument("--gripper-open", default="M4 S40", help="열기 명령 (W4 · robot/inverse_kinematics.py)")
    parser.add_argument("--gripper-close", default="M4 S60", help="닫기 명령")
    parser.add_argument("--every", type=int, default=1,
                        help="N 스텝마다 한 줄만 적는다. Mirobot 이 20Hz 를 못 따라갈 때 (W5 CHECKLIST 2-4)")
    parser.add_argument("--chunk", type=int, default=16, help="라벨에 쓸 chunk 길이. policy 가 한 번에 내는 수")
    parser.add_argument("--log-dir", type=Path, default=Path("data") / "translate")


def convert(meta: dict, rows: list[dict], args, source: str, title: str) -> tuple[list[str], list[dict], dict]:
    """(G-code 줄, Mirobot 행, 기록 meta). 파일은 쓰지 않는다."""
    try:
        ref_mirobot, scale = resolve_mapping(args.mapping, args.point)
    except ValueError as e:
        raise SystemExit(str(e))
    if args.scale is not None:
        scale = args.scale

    ref_q = quat_xyzw_to_wxyz(tuple(meta["start_eef_quat_xyzw"]))
    ref_flange = grip_to_flange(meta["start_eef_pos"], ref_q)
    out_rows = []
    for row in rows:
        q = quat_xyzw_to_wxyz(tuple(row["eef_quat_xyzw"]))
        flange = grip_to_flange(row["eef_pos"], q)
        q_mirobot = (libero_to_mirobot_quat(q) if args.orientation == "absolute"
                     else quat_mul(q, quat_conj(ref_q)))
        xyz = libero_to_mirobot_flange_mm(flange, q, q_mirobot, ref_flange, ref_q, args.point, scale, ref_mirobot)
        abc = quat_to_euler_xyz_deg(q_mirobot)
        k = row["step"]
        out_rows.append({"step": k, "chunk": (k - 1) // args.chunk + 1, "action": row.get("action"),
                         "done": row.get("done", row.get("goal")),
                         "eef_pos": row["eef_pos"], "eef_quat_xyzw": row["eef_quat_xyzw"],
                         "mirobot_xyz_mm": [round(v, 2) for v in xyz],
                         "mirobot_abc_deg": [round(v, 2) for v in abc],
                         "reach_mm": round(math.hypot(xyz[0], xyz[1]), 2)})

    # 그리퍼 — 부호가 바뀌는 첫 스텝 앞에 M4 한 줄을 넣고, 그 스텝은 --every 와 무관하게 남긴다
    gripper_at = {}
    if args.gripper:
        if any(r["action"] is None for r in out_rows):
            raise SystemExit("--gripper 는 행마다 action 이 있어야 한다 (action[6] 의 부호를 본다)")
        sign = None
        for r in out_rows:
            now = 1 if r["action"][6] > 0 else -1
            if now != sign:
                gripper_at[r["step"]] = args.gripper_close if now > 0 else args.gripper_open
                sign = now
    last = out_rows[-1]["step"]
    # 그리퍼가 바뀌는 스텝 k 의 action 은 스텝 k-1 의 자세에서 시작한다. 그래서 k-1 도 남겨야
    # Mirobot 이 그 자세에 도착한 뒤 M4 를 실행한다. --every 로 k-1 이 빠지면 몇 스텝 앞(예: 잡는 높이보다
    # 15 mm 위)에서 집게가 닫힌다 (10/11, --every 5 에서 발견)
    before_gripper = {k - 1 for k in gripper_at}
    kept = [r for r in out_rows if r["step"] % args.every == 0 or r["step"] == last
            or r["step"] in gripper_at or r["step"] in before_gripper]

    which = "파지점 ↔ 파지점" if args.point == "grip" else "플랜지 ↔ 플랜지"
    pair = f"{which}, Panda 시작 ↔ Mirobot {tuple(round(v, 2) for v in ref_mirobot)} (짝 {args.mapping}), 배율 {scale:g}"
    lines = [f"; {title}",
             f"; 출처 {source}  {meta.get('scene') or meta.get('bddl') or ''}".rstrip(),
             f"; F = x축 180°, {pair}, orientation {args.orientation}",
             f"; 스텝 {len(out_rows)}개 중 {len(kept)}줄 (every {args.every}), chunk {args.chunk}",
             point_marker(args.point), pair_marker(ref_mirobot, scale), "G90", "M20"]
    if gripper_at:
        lines.insert(4, "; 그리퍼 M4 포함 — run_gcode --auto 로만 실행한다 (--stream 은 M4 를 앞에 몰아 보낸다)")
    for r in kept:
        x, y, z = r["mirobot_xyz_mm"]
        a, b, c = r["mirobot_abc_deg"]
        if r["step"] in gripper_at:
            # 앞 줄의 G0 에 도착한 뒤(--auto) 개폐한다. 닫히는 시간은 아직 안 쟀다 — 뒤따르는 같은 자리 G0 들이 기다림이 된다
            lines += [f"; gripper s{r['step']:04d}", gripper_at[r["step"]]]
        lines += [f"; c{r['chunk']:02d}s{r['step']:04d}",
                  f"G0 X{x:.2f} Y{y:.2f} Z{z:.2f} A{a:.2f} B{b:.2f} C{c:.2f}"]

    # 역변환 검산 — 파일에 쓴 (반올림된) 값을 Panda 손 좌표로 되돌려 원래와 댄다 (Mirobot mm 기준).
    # 나갈 때와 들어올 때 같은 F · L 을 쓰므로 그 오차는 상쇄돼 안 보인다 (roundtrip_check 와 같은 한계)
    worst_pos = 0.0
    for r in out_rows:
        q_m = euler_xyz_deg_to_quat(*r["mirobot_abc_deg"])
        q_l = (mirobot_to_libero_quat(q_m) if args.orientation == "absolute" else quat_mul(q_m, ref_q))
        back = flange_to_grip(mirobot_to_libero_flange_m(r["mirobot_xyz_mm"], q_m, q_l, ref_flange, ref_q,
                                                          args.point, scale, ref_mirobot), q_l)
        worst_pos = max(worst_pos, math.dist(back, r["eef_pos"]) * 1000 * scale)

    log_meta = {"source": source, "source_meta": meta, "task": meta.get("task"),
                "orientation": args.orientation, "point": args.point, "every": args.every,
                "mapping": args.mapping, "ref_mirobot_mm": list(ref_mirobot), "scale": scale,
                "start_flange_m": list(ref_flange), "start_quat_wxyz": list(ref_q),
                "gripper": {str(k): v for k, v in gripper_at.items()}}
    return lines, out_rows, {"meta": log_meta, "kept": kept, "gripper_at": gripper_at,
                             "roundtrip_mm": worst_pos}


def report(kept: list[dict], rows: list[dict], gripper_at: dict, roundtrip_mm: float | None = None) -> None:
    """표 몇 줄과 경고. 세로 하한은 경고만 하고 값은 그대로 둔다 — 실제로 막는 것은 run_gcode 다."""
    reach = max(r["reach_mm"] for r in kept)
    angle = max(max(abs(v) for v in r["mirobot_abc_deg"]) for r in kept)
    z_lo = min(r["mirobot_xyz_mm"][2] for r in kept)
    over_reach = [r["step"] for r in kept if r["reach_mm"] > REACH_WARN_MM]
    over_angle = [r["step"] for r in kept if max(abs(v) for v in r["mirobot_abc_deg"]) > ANGLE_WARN_DEG]
    # 잘라 쓰면 원래 동작과 Mirobot 동작이 몰래 달라진다
    below_floor = [r["step"] for r in kept if r["mirobot_xyz_mm"][2] < Z_FLOOR_MM]
    low_z = [r["step"] for r in kept if Z_FLOOR_MM <= r["mirobot_xyz_mm"][2] < Z_WARN_MM]
    print(f"{'스텝':>6} {'chunk':>5} | {'X':>8} {'Y':>8} {'Z':>8} mm | {'A':>7} {'B':>7} {'C':>7} ° | {'수평':>6}")
    for r in kept[:3] + (["..."] if len(kept) > 6 else []) + kept[-3:]:
        if r == "...":
            print(f"{'...':>6}")
            continue
        x, y, z = r["mirobot_xyz_mm"]
        a, b, c = r["mirobot_abc_deg"]
        print(f"{r['step']:6d} {r['chunk']:5d} | {x:8.2f} {y:8.2f} {z:8.2f} | {a:7.2f} {b:7.2f} {c:7.2f} | {r['reach_mm']:6.1f}")
    if gripper_at:
        print("그리퍼 " + ", ".join(f"스텝 {k} {v}" for k, v in gripper_at.items()))
    print(f"\n{len(rows)}스텝 → G0 {len(kept)}줄.  수평 최대 {reach:.1f}mm (경고선 {REACH_WARN_MM:.0f}), "
          f"각도 최대 {angle:.1f}° (경고선 {ANGLE_WARN_DEG:.0f}), "
          f"Z 최저 {z_lo:.1f}mm (하한 {Z_FLOOR_MM:g} · 경고선 {Z_WARN_MM:g})")
    if over_reach:
        print(f"  !! 수평 경고선 넘은 줄 {len(over_reach)}개 — 처음 {over_reach[:5]}")
    if over_angle:
        print(f"  !! 각도 경고선 넘은 줄 {len(over_angle)}개 — 처음 {over_angle[:5]}")
    if below_floor:
        print(f"  !! Z 하한 {Z_FLOOR_MM:g}mm 아래 줄 {len(below_floor)}개 — 처음 {below_floor[:5]} "
              f"(run_gcode 가 보내지 않는다)")
    if low_z:
        print(f"  !  Z {Z_WARN_MM:g}mm 아래 줄 {len(low_z)}개 — 처음 {low_z[:5]}")
    if not (over_reach or over_angle or below_floor or low_z):
        print("  경고 없음")
    if roundtrip_mm is not None:
        print(f"역변환 검산 — 파일 값으로 되돌린 손 좌표와 원래의 차이 최대 {roundtrip_mm:.3f}mm (Mirobot 기준, 반올림 크기)")


def write_outputs(lines: list[str], rows: list[dict], info: dict, out_path: Path, log_dir: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")  # 읽는 쪽이 utf-8 로 읽는다
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{time.strftime('%Y_%m_%d-%H_%M_%S')}.jsonl"
    with log_path.open("w", encoding="utf-8") as log:
        log.write(json.dumps({"meta": info["meta"]}, ensure_ascii=False) + "\n")
        for row in rows:
            log.write(json.dumps(row) + "\n")
    return log_path


def default_out(source: Path) -> Path:
    return Path("trajectories") / f"{time.strftime('%Y_%m_%d')}-translated-{source.stem}.gcode"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--poses", type=Path, required=True, help="손 좌표 JSONL (pickup.py --log · action_to_poses.py)")
    add_arguments(parser)
    args = parser.parse_args()
    meta, rows = read_poses(args.poses)
    lines, out_rows, info = convert(meta, rows, args, str(args.poses),
                                    "Panda 손 좌표 → Mirobot  (tools/poses_to_gcode.py)")
    print(f"손 좌표 {len(rows)}스텝 — {args.poses}")
    print(f"orientation {args.orientation}, point {args.point}, every {args.every}")
    print(f"짝 {args.mapping} — Mirobot 쪽 {tuple(round(v, 2) for v in info['meta']['ref_mirobot_mm'])} mm, "
          f"배율 {info['meta']['scale']:g}\n")
    report(info["kept"], out_rows, info["gripper_at"], info["roundtrip_mm"])
    out = args.out or default_out(args.poses)
    log_path = write_outputs(lines, out_rows, info, out, args.log_dir)
    print(f"saved {out}\nsaved {log_path}")


if __name__ == "__main__":
    main()
