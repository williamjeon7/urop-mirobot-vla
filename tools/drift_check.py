#!/usr/bin/env python3
"""W4 ④ 오차 누적 판정 — 추종 기록을 **순서대로** 읽어 waypoint 순서 `k` 에 대한 회귀 기울기를 낸다.

    # 검산 — 9/21 짧은 기록. 끝값이 이미 아는 2.09mm 와 맞아야 한다 (CHECKLIST 5-3)
    python -m tools.drift_check --log data/follow/2026_09_21-09_45_06.jsonl \
        --orientation relative --reference data/compound/2026_09_17-10_44_39.jsonl

    # 9/28 긴 궤적 둘. --plot 은 matplotlib 이 있는 환경에서 (서버 cosmos-policy .venv)
    python -m tools.drift_check --log data/follow/2026_09_28-10_36_55.jsonl \
                               --log data/follow/2026_09_28-10_35_26.jsonl \
                               --plot rollouts/2026_09_28/drift/drift.png

**왜 새 파일인가** — `roundtrip_check extract` 는 **좌표로** waypoint 를 찾는다. 같은 자리를 여러 번 밟는
반복 궤적에서는 회차가 하나로 합쳐져 버린다. 여기는 기록을 **순서대로** 읽어 라벨이 바뀌는 자리로 방문을
끊으므로, 같은 라벨의 재방문이 회차별로 남는다 (CHECKLIST 5-3).

**지표는 ② 와 같다** (`roundtrip_check` 와 같은 함수·같은 정의). 새 지표를 만들지 않았다.
  위치  두 점 사이 3D 직선거리 — **플랜지와 파지점을 따로** (`common/workspace.py`)
  자세  두 자세를 겹치는 데 필요한 **최소 회전각** (`roundtrip_check.angle_deg`)

**크기가 아니라 기울기가 답이다.** 기본 기준선은 *목표 대비 잔차*인데, 그 크기는 오차가 아니라 우리가 고른
멈춤 기준이다 (ANSWER ② 4항 — 2mm 기준에서 멈추니 ≤1.90mm 가 나온다). 기준을 조이면 같이 내려간다.
누적 판정에 쓸 수 있는 것은 그 값이 `k` 에 따라 **커지는가** 뿐이다.

`--reference` 를 주면 *원본 Panda 롤아웃 대비* 오차도 같이 낸다 — 변환·실물·잔차가 겹친 "끝에서 끝" 이고,
9/21 기록에서 파지점 2.09mm · 플랜지 2.49mm · 자세 0.35° 가 나오는 그 숫자다 (검산용).
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from common.rotation import euler_xyz_deg_to_quat, mirobot_to_libero_quat, quat_mul, quat_xyzw_to_wxyz
from common.workspace import (
    LEGACY_POINT,
    POINTS,
    flange_to_grip,
    grip_to_flange,
    mirobot_to_libero_flange_m,
    read_pair_marker,
    read_point_marker,
)
from tools.roundtrip_check import angle_deg
from tools.run_gcode import parse_file, pose_of

# 반복 궤적의 라벨 = 회차 + 방향 + 원래 이름. "r1 home1", "r2f seg1-end", "r3b start"
ROUND_RE = re.compile(r"^r(\d+)([fb]?)\s+(.+)$")

METRICS = (("파지점", "mm"), ("플랜지", "mm"), ("자세", "°"))


def split_label(label: str) -> tuple[int, str, str]:
    """라벨 → (회차, 방향, 원래 이름). 회차가 없는 라벨은 1회차로 본다.

    방향을 이름에 붙여 둔다 — 왕복 궤적은 한 회차 안에서 같은 이름을 두 번(가는 길·돌아오는 길) 밟으므로
    `seg1-end` 하나로 묶으면 그 둘이 섞인다.
    """
    m = ROUND_RE.match(label)
    if m is None:
        return 1, "", label
    return int(m.group(1)), m.group(2), m.group(3)


def read_visits(log_path: Path) -> tuple[dict, list[dict]]:
    """추종 기록 → (meta, 방문 목록). **라벨이 바뀌는 자리로 끊는다** — 좌표로 찾지 않는다."""
    rows = [json.loads(line) for line in log_path.open(encoding="utf-8")]
    meta = rows[0]["meta"] if "meta" in rows[0] else {}
    visits: list[dict] = []
    for row in rows:
        if "meta" in row:
            continue
        if visits and visits[-1]["label"] == row["waypoint"]:
            visits[-1]["steps"] += 1
            visits[-1]["last"] = row
            continue
        visits.append({"label": row["waypoint"], "steps": 1, "last": row})
    for k, visit in enumerate(visits, 1):
        visit["k"] = k
        visit["round"], visit["dir"], visit["base"] = split_label(visit["label"])
        visit["key"] = f"{visit['dir']} {visit['base']}".strip()
        last = visit["last"]
        visit["p_grip"] = tuple(last["eef_pos"])
        visit["quat"] = quat_xyzw_to_wxyz(tuple(last["eef_quat_xyzw"]))
        visit["p_flange"] = grip_to_flange(visit["p_grip"], visit["quat"])
        visit["logged"] = (last["gap_mm"], last["gap_deg"])
    return meta, visits


def read_targets(gcode: Path, start_flange_m, start_quat, orientation: str = "absolute",
                 point: str = LEGACY_POINT) -> list[tuple[str, tuple, tuple]]:
    """G-code → (이름, 플랜지 위치 m, 플랜지 자세 wxyz). `tools/libero_follow.targets_from_gcode` 와 같은 식.

    libero 를 끌어오지 않으려고 여기 다시 적었다 — `libero_follow` 는 import 만으로 시뮬레이터가 붙는다.
    맞게 옮겼는지는 아래 `check_self` 가 기록의 `gap_mm`·`gap_deg` 와 대 봐서 확인한다.
    `start_quat`(Panda 시작 자세)는 relative 이거나 파지점 기준일 때만 쓴다 — 옛 플랜지·absolute 기록은 None 이어도 된다.
    """
    ref_mirobot, scale = read_pair_marker(gcode.read_text(encoding="utf-8"), point)  # 없으면 홈·배율 1
    out = []
    for label, command in parse_file(gcode):
        pose = pose_of(command)
        if pose is None:
            continue
        q_mirobot = euler_xyz_deg_to_quat(*pose[3:6])
        q = quat_mul(q_mirobot, start_quat) if orientation == "relative" else mirobot_to_libero_quat(q_mirobot)
        p = mirobot_to_libero_flange_m(pose[:3], q_mirobot, q, start_flange_m, start_quat, point, scale, ref_mirobot)
        out.append((label or f"wp{len(out) + 1}", p, q))
    return out


def read_reference(rollout: Path) -> dict[str, dict]:
    """원본 롤아웃 → {waypoint 이름: 그 줄}. 끝에서 끝 비교의 기준이다."""
    rows = [json.loads(line) for line in rollout.open(encoding="utf-8")]
    return {r["waypoint"]: r for r in rows if r.get("waypoint")}


def errors_to_target(visit: dict, target: tuple) -> tuple[float, float, float]:
    """(파지점 mm, 플랜지 mm, 자세 °) — 목표 대비 잔차."""
    _, t_flange, t_quat = target
    return (math.dist(visit["p_grip"], flange_to_grip(t_flange, t_quat)) * 1000.0,
            math.dist(visit["p_flange"], t_flange) * 1000.0,
            angle_deg(visit["quat"], t_quat))


def errors_to_reference(visit: dict, row: dict) -> tuple[float, float, float]:
    """(파지점 mm, 플랜지 mm, 자세 °) — 원본 Panda 롤아웃 대비 "끝에서 끝"."""
    return (math.dist(visit["p_grip"], row["eef_pos"]) * 1000.0,
            math.dist(visit["p_flange"], row["flange_pos"]) * 1000.0,
            angle_deg(visit["quat"], quat_xyzw_to_wxyz(tuple(row["eef_quat_xyzw"]))))


def ols(xs, ys) -> tuple[float, float, float]:
    """(기울기, 절편, 기울기의 표준오차). 표본이 2개 이하면 표준오차는 0 으로 둔다."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my, 0.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    if n <= 2:
        return slope, intercept, 0.0
    sse = sum((y - intercept - slope * x) ** 2 for x, y in zip(xs, ys))
    return slope, intercept, math.sqrt(sse / (n - 2) / sxx)


def check_self(visits, series) -> float:
    """재구성한 목표가 맞는지 — 기록에 남은 `gap_mm`·`gap_deg` 와 대 본다. 0 이어야 한다."""
    worst = 0.0
    for visit, (grip, _, rot) in zip(visits, series):
        worst = max(worst, abs(grip - visit["logged"][0]), abs(rot - visit["logged"][1]))
    return worst


def start_quat_of(meta: dict, reference: dict | None) -> tuple | None:
    """relative 로 읽은 기록의 목표를 되살리려면 Panda 시작 자세가 필요하다.

    기록에 없으면(9/20~21 기록) 원본 롤아웃의 첫 waypoint 에서 가져온다 — 같은 task·같은 seed·같은
    settle 30스텝이라 같은 자세다 (플랜지 위치가 4e-8 m 안에서 일치하는 것으로 확인).
    """
    if meta.get("start_flange_quat_wxyz"):
        return tuple(meta["start_flange_quat_wxyz"])
    if reference:
        first = next(iter(reference.values()))
        return quat_xyzw_to_wxyz(tuple(first["flange_quat_xyzw"]))
    return None


def analyse(log_path: Path, args) -> dict:
    """기록 하나를 읽어 표를 찍고, 회귀와 회차 비교에 쓸 것을 돌려준다."""
    meta, visits = read_visits(log_path)
    gcode = Path(args.gcode or meta.get("source", ""))
    orientation = args.orientation or meta.get("orientation") or "absolute"
    reference = read_reference(args.reference) if args.reference else None

    # 어느 점끼리 맞춘 기록인가 — --point > 기록 meta (9/30 부터) > G-code 머리말 > 표시 없음 = 플랜지 (옛 기록)
    point = (args.point or meta.get("point")
             or (read_point_marker(gcode.read_text(encoding="utf-8")) if gcode.is_file() else None) or LEGACY_POINT)
    needs_quat = orientation == "relative" or point == "grip"
    ref_quat = start_quat_of(meta, reference) if needs_quat else None
    if needs_quat and ref_quat is None:
        raise SystemExit(f"{log_path}: {orientation}·{point} 기록인데 시작 자세를 모른다 — --reference 를 같이 줄 것")
    targets = read_targets(gcode, meta["start_flange_m"], ref_quat, orientation, point)
    if [label for label, _, _ in targets] != [v["label"] for v in visits]:
        raise SystemExit(f"{log_path}: waypoint 목록이 {gcode} 와 다르다 — --gcode 를 확인할 것\n"
                         f"  기록 {len(visits)}개, 파일 {len(targets)}개")

    residual = [errors_to_target(v, t) for v, t in zip(visits, targets)]
    gap = check_self(visits, residual)
    end_to_end = None
    if reference:
        missing = [v["base"] for v in visits if v["base"] not in reference]
        if missing:
            raise SystemExit(f"{log_path}: 원본 롤아웃에 없는 waypoint {sorted(set(missing))}")
        end_to_end = [errors_to_reference(v, reference[v["base"]]) for v in visits]

    rounds = sorted({v["round"] for v in visits})
    print(f"\n{'=' * 100}\n{log_path}  ←  {gcode}  (orientation {orientation}, point {point})")
    print(f"waypoint {len(visits)}개 · {sum(v['steps'] for v in visits)}스텝 · 회차 {len(rounds)}"
          f" · 멈춤 기준 {meta.get('pos_tol_mm')}mm · {meta.get('rot_tol_deg')}°")
    borrowed = needs_quat and not meta.get("start_flange_quat_wxyz")
    print(f"목표 재구성 검산 — 기록의 gap 과 최대 차이 {gap:.2e} (mm · °)"
          + ("  ← 시작 자세를 원본 롤아웃에서 빌려 온 몫" if borrowed else "  ← 0 이어야 한다"))
    if gap > (1e-3 if borrowed else 1e-9):
        raise SystemExit(f"{log_path}: 목표를 잘못 되살렸다 — --gcode · --orientation 을 확인할 것")

    head = f"{'k':>3} {'waypoint':16} {'스텝':>4} | {'목표 대비 잔차':>26}"
    if end_to_end:
        head += f" | {'원본 대비 (끝에서 끝)':>26}"
    print(f"\n{head}\n{'':>3} {'':16} {'':>4} | {'파지점':>8} {'플랜지':>8} {'자세':>8}"
          + (f" | {'파지점':>8} {'플랜지':>8} {'자세':>8}" if end_to_end else ""))
    for i, visit in enumerate(visits):
        line = (f"{visit['k']:3d} {visit['label']:16} {visit['steps']:4d} | "
                f"{residual[i][0]:7.3f}mm {residual[i][1]:7.3f}mm {residual[i][2]:7.3f}°")
        if end_to_end:
            line += f" | {end_to_end[i][0]:7.3f}mm {end_to_end[i][1]:7.3f}mm {end_to_end[i][2]:7.3f}°"
        print(line)

    out = {"log": log_path, "gcode": gcode, "meta": meta, "visits": visits,
           "residual": residual, "end_to_end": end_to_end, "rounds": rounds}
    report_slope(out)
    report_rounds(out)
    return out


def report_slope(out: dict) -> None:
    """waypoint 순서 k 에 대한 회귀 기울기 — ④ 의 답이 되는 숫자."""
    ks = [v["k"] for v in out["visits"]]
    n = len(ks)
    for title, series in (("목표 대비 잔차", out["residual"]), ("원본 대비 (끝에서 끝)", out["end_to_end"])):
        if series is None:
            continue
        print(f"\n[{title}]  waypoint 순서 k 에 대한 회귀   (k = 1 … {n})")
        print(f"{'':10} {'평균':>9} {'최대':>9} | {'기울기 (단위/waypoint)':>24} | {'궤적 전체 예상 증가':>18}")
        for (name, unit), values in zip(METRICS, zip(*series)):
            slope, _, se = ols(ks, values)
            print(f"{name:10} {sum(values) / n:8.3f}{unit:<2} {max(values):8.3f}{unit:<2} | "
                  f"{slope:+10.3e} ± {2 * se:8.1e} {unit:>3}/wp | {slope * (n - 1):+8.3f}{unit}")
        print("  ± 는 기울기의 2 표준오차 (≈95%). 0 을 품으면 \"k 에 따라 커진다\" 고 말할 수 없다")


def group_rounds(out: dict) -> dict[str, list[tuple[int, float, float, float]]]:
    """{waypoint 이름: [(회차, 파지점, 플랜지, 자세), …]} — 같은 자리를 다시 밟은 것끼리 묶는다."""
    groups: dict[str, list] = {}
    for visit, err in zip(out["visits"], out["residual"]):
        groups.setdefault(visit["key"], []).append((visit["round"], *err))
    return {key: sorted(rows) for key, rows in groups.items() if len(rows) > 1}


def report_rounds(out: dict) -> None:
    """같은 waypoint 의 1회차 vs 마지막 회차. 누적이 있으면 여기서 벌어진다."""
    groups = group_rounds(out)
    if not groups:
        print("\n반복 방문이 없다 — 회차 비교를 건너뛴다")
        return
    print(f"\n[같은 waypoint 를 다시 밟은 것]  {len(groups)}곳, 회차 {out['rounds']}")
    print(f"{'waypoint':16} {'회차':>4} | {'1회차 파지점':>12} {'마지막 파지점':>13} {'차이':>9}"
          f" | {'1회차 자세':>11} {'마지막 자세':>12} {'차이':>9}")
    worst_pos = worst_rot = 0.0
    for key, rows in groups.items():
        first, last = rows[0], rows[-1]
        d_pos, d_rot = last[1] - first[1], last[3] - first[3]
        worst_pos, worst_rot = max(worst_pos, abs(d_pos)), max(worst_rot, abs(d_rot))
        print(f"{key:16} {len(rows):4d} | {first[1]:10.3f}mm {last[1]:11.3f}mm {d_pos:+7.3f}mm"
              f" | {first[3]:10.3f}° {last[3]:11.3f}° {d_rot:+8.3f}°")
    print(f"\n마지막 회차 − 1회차, 절댓값 최대 — 파지점 {worst_pos:.3f}mm, 자세 {worst_rot:.3f}°")

    means = {r: [v for v, visit in zip((e[0] for e in out["residual"]), out["visits"]) if visit["round"] == r]
             for r in out["rounds"]}
    print("회차별 파지점 잔차 평균 — " + ", ".join(
        f"r{r} {sum(v) / len(v):.3f}mm" for r, v in means.items() if v))


def plot(results: list[dict], path: Path) -> None:
    """미팅에 가져갈 그림 한 장. 행은 궤적, 왼쪽은 순서 vs 오차 + 회귀선, 오른쪽은 1회차 vs 마지막 회차."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    # 한글이 되는 첫 글꼴. Noto CJK 는 .ttc 라 KR 이 아니라 JP 이름으로 잡히는데 한글 글자는 같이 들어 있다.
    # Baekmuk 은 em dash(—) 가 없어 뒤로 둔다
    have = {f.name for f in font_manager.fontManager.ttflist}
    korean = next((f for f in ("Noto Sans CJK KR", "Noto Sans CJK JP", "NanumGothic", "UnDotum",
                               "Baekmuk Gulim") if f in have), None)
    if korean:
        plt.rcParams["font.family"] = korean
    plt.rcParams["axes.unicode_minus"] = False

    fig, axes = plt.subplots(len(results), 2, figsize=(15, 4.6 * len(results)), squeeze=False)
    for row, out in enumerate(results):
        ks = [v["k"] for v in out["visits"]]
        grip, flange, rot = (list(v) for v in zip(*out["residual"]))
        name = out["gcode"].stem
        ax = axes[row][0]

        for r in out["rounds"][1:]:  # 회차 경계
            ax.axvline(min(v["k"] for v in out["visits"] if v["round"] == r) - 0.5,
                       color="0.8", ls=":", lw=1, zorder=0)
        for r in out["rounds"]:
            first = min(v["k"] for v in out["visits"] if v["round"] == r)
            ax.annotate(f"r{r}", (first, 1.0), xycoords=("data", "axes fraction"),
                        va="top", ha="left", fontsize=8, color="0.45")

        ax.plot(ks, grip, "o-", ms=3.5, lw=0.8, color="#1f77b4", label="파지점 (mm)")
        ax.plot(ks, flange, "s-", ms=3.0, lw=0.8, color="#2ca02c", alpha=0.75, label="플랜지 (mm)")
        lines = []
        for values, color in ((grip, "#1f77b4"), (flange, "#2ca02c")):
            slope, intercept, se = ols(ks, values)
            ax.plot(ks, [intercept + slope * k for k in ks], "-", color=color, lw=2.2, alpha=0.5)
            lines.append(f"{slope:+.2e} ± {2 * se:.1e} mm/wp")
        tol = out["meta"].get("pos_tol_mm")
        if tol:  # 잔차의 크기는 여기서 멈춘 결과다 — 오차가 아니라 우리가 고른 값 (ANSWER ② 4항)
            ax.axhline(tol, color="0.35", ls="--", lw=1.1)
            ax.annotate(f"멈춤 기준 {tol:g}mm (파지점)", (0.99, tol), xycoords=("axes fraction", "data"),
                        va="bottom", ha="right", fontsize=8, color="0.35")
        ax.set_xlabel("waypoint 순서 k")
        ax.set_ylabel("목표 대비 잔차 (mm)")
        ax.set_ylim(0, max(max(grip), max(flange)) * 1.35 + 0.1)

        twin = ax.twinx()
        twin.plot(ks, rot, "x--", ms=3.5, lw=0.7, color="#d62728", alpha=0.7, label="자세 (°)")
        slope, intercept, se = ols(ks, rot)
        twin.plot(ks, [intercept + slope * k for k in ks], "-", color="#d62728", lw=2.2, alpha=0.5)
        twin.set_ylabel("자세 잔차 (°)", color="#d62728")
        twin.tick_params(axis="y", colors="#d62728")
        twin.set_ylim(0, max(rot) * 1.35 + 0.02)
        lines.append(f"{slope:+.2e} ± {2 * se:.1e} °/wp")

        ax.set_title(f"{name}  —  waypoint {len(ks)}개, {sum(v['steps'] for v in out['visits'])}스텝", fontsize=10)
        ax.text(0.015, 0.035, "기울기   파지점 " + lines[0] + "\n           플랜지 " + lines[1]
                + "\n           자세    " + lines[2], transform=ax.transAxes, fontsize=8.5,
                va="bottom", family=korean or "monospace",
                bbox=dict(fc="white", ec="0.7", alpha=0.9, boxstyle="round,pad=0.4"))
        handles = ax.get_legend_handles_labels()[0] + twin.get_legend_handles_labels()[0]
        ax.legend(handles, ["파지점 (mm)", "플랜지 (mm)", "자세 (°)"], loc="upper right", fontsize=8)

        ax = axes[row][1]
        groups = group_rounds(out)
        keys = list(groups)
        xs = range(len(keys))
        first = [groups[k][0][1] for k in keys]
        last = [groups[k][-1][1] for k in keys]
        ax.bar([x - 0.2 for x in xs], first, 0.4, color="#1f77b4", label=f"1회차 (r{out['rounds'][0]})")
        ax.bar([x + 0.2 for x in xs], last, 0.4, color="#ff7f0e", label=f"마지막 회차 (r{out['rounds'][-1]})")
        ax.set_xticks(list(xs))
        ax.set_xticklabels(keys, rotation=60, ha="right", fontsize=7.5)
        ax.set_ylabel("목표 대비 잔차 · 파지점 (mm)")
        worst = max(abs(a - b) for a, b in zip(first, last))
        ax.set_title(f"같은 waypoint — 1회차 vs 마지막 회차   (최대 차이 {worst:.3f}mm)", fontsize=10)
        ax.legend(fontsize=8)
        ax.set_ylim(0, max(max(first), max(last)) * 1.25 + 0.05)

    fig.suptitle("W4 ④ Panda(시뮬) 오차 누적 — waypoint 순서에 대한 회귀. 잔차의 크기는 우리가 고른 "
                 "멈춤 기준이고, 판정은 기울기로 한다", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    print(f"\nsaved {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", type=Path, action="append", required=True,
                        help="추종 기록 jsonl (data/follow/). 여러 번 주면 그림에 행으로 쌓인다")
    parser.add_argument("--gcode", type=Path, help="목표 G-code. 기본은 기록 meta 의 source")
    parser.add_argument("--orientation", choices=("absolute", "relative"),
                        help="기본은 기록 meta 의 값. 9/20~21 기록에는 없어 직접 줘야 한다")
    parser.add_argument("--point", choices=POINTS,
                        help="어느 점끼리 맞춘 기록인지. 기본은 기록 meta → G-code 머리말 → flange (9/28 까지의 기록)")
    parser.add_argument("--reference", type=Path,
                        help="원본 Panda 롤아웃 jsonl — 주면 '끝에서 끝' 도 같이 낸다 (검산용)")
    parser.add_argument("--plot", type=Path, help="그림을 쓸 경로 (matplotlib 필요)")
    args = parser.parse_args()

    results = [analyse(log, args) for log in args.log]
    if args.plot:
        plot(results, args.plot)


if __name__ == "__main__":
    main()
