#!/usr/bin/env python3
"""W9 3-2 시뮬 Panda 따라가기 — Mirobot 기록 → 칸마다 외부 영상 · action · proprio. (`cosmos-policy/.venv`)

배경 — Mirobot 쪽 카메라는 손목 하나라 외부 영상은 시뮬 Panda 것을 쓴다. 시뮬과 실물은 같은 속도로 움직이지 않으므로,
녹화가 끝난 뒤 시뮬 Panda 가 실물 자세 기록을 0.05 s 격자로 따라가며 외부 영상과 action 라벨을 새로 만든다 ((나) 방식, 10/28).
설계·결정·결과는 `docs/W9/FOLLOW.md`. 손목 프레임은 여기서 다루지 않는다 — 나중에 칸 시각 `t` 로 골라 붙인다.

    # 가짜 실물 기록 — W6 시뮬 pick up 을 10/5 실측대로 느리고 고르지 않게 (영상 없이 시험할 때)
    cosmos-policy/.venv/bin/python -m tools.follow_record --fake docs/W6/poses/pickup-red-s2.jsonl \\
        --gcode trajectories/2026_10_11-w6-pickup-red-s2-e5.gcode --slow 2.34
    # run_gcode --stream 기록 (블록 없는 궤적이면 장면은 --poses 로 아무 W6 기록이나 — 오차만 본다)
    cosmos-policy/.venv/bin/python -m tools.follow_record --run-gcode-log data/gcode_run/<기록>.jsonl --gcode <그 G-code>

한 칸 k (t_k = t_0 + k·0.05 s):
  외부 영상   action k 를 내기 **전** 시뮬 agentview (256, np.flipud)
  action k    `servo_action` — 목표는 **t_(k+1)** 의 실물 자세 (한 칸 앞, FOLLOW.md 2절)
  proprio     실물 t_k 자세 → Panda 형식 (`common/proprio.py`), 손가락은 B' — 그리퍼 명령 시각부터 `--close-s` 동안 열림 → 잡음
  오차        시뮬 손 vs 실물 손 (Mirobot 기준 mm, 도)

남는 것 — `<--out>/<이름>.hdf5`: t, agentview_rgb, actions, robot_states(실물), sim_robot_states, err_mm, err_deg, gripper_cmd
그리고 meta(입력 파일, 설정, 시뮬 성공, no-op 수, 오차 요약).
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import random
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 무엇도 받지 않는다 (① 408MB 사고). `.venv` LIBERO 의 "Downloading" 문구는 캐시를 찾고 끝난다
sys.path.insert(0, str(REPO / "docs" / "W6" / "rgb_blocks"))

import h5py  # noqa: E402
import numpy as np  # noqa: E402

from common.proprio import fingers, mirobot_to_libero_pose, robot_states, settings_from_gcode  # noqa: E402
from common.rotation import (libero_to_mirobot_quat, quat_normalize, quat_to_euler_xyz_deg,  # noqa: E402
                             quat_xyzw_to_wxyz)
from common.servo import pose_gap, servo_action  # noqa: E402
from common.workspace import grip_to_flange, libero_to_mirobot_flange_mm  # noqa: E402

DT = 0.05            # LIBERO 제어 주기 — 바꾸지 않는다 (action 번역의 전제)
NOOP_THRESHOLD = 1e-4  # regenerate_libero_dataset.py:89
SOURCE_RE = re.compile(r"^;\s*출처\s+(\S+\.jsonl)", re.MULTILINE)


# ── Mirobot 기록 — 모든 입력을 같은 모양으로 ─────────────────────────────
# {"samples": [(t, [X, Y, Z, A, B, C]), …],  "gripper": [(t, "close"|"open"), …]}  t 는 초(시스템 시각 또는 0 부터)

def gripper_kind(command: str, open_s: int, close_s: int) -> str | None:
    m = re.match(r"M4\s+S(\d+)", command.strip())
    if not m:
        return None
    s = int(m.group(1))
    return "close" if abs(s - close_s) < abs(s - open_s) else "open"


def record_from_run_gcode(path: Path, open_s: int, close_s: int) -> dict:
    """`run_gcode` 기록. --stream 이면 `stream` 줄의 rows(t_s, cart)를, 아니면 `waypoint` 줄을 쓴다.

    t_s 는 프로세스 안 상대 시각이라, 첫 `stream_send` 의 시스템 시각(t_wall − t_s)으로 시스템 시각에 맞춘다.
    """
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    sends = [r for r in rows if r.get("kind") == "stream_send"]
    streams = [r for r in rows if r.get("kind") == "stream"]
    samples, gripper = [], []
    if streams:
        t0 = sends[0]["t_wall"] - sends[0]["t_s"] if sends else 0.0
        for row in streams[-1]["rows"]:
            if row.get("cart") and len(row["cart"]) >= 6:
                samples.append((t0 + row["t_s"], list(row["cart"][:6])))
    else:  # --auto: waypoint 도착만 남는다 — 이동 중 자세가 없다 (FOLLOW.md 참고)
        for r in rows:
            if r.get("kind") == "waypoint" and r.get("reported"):
                samples.append((r["t_wall"], list(r["reported"][:6])))
    for r in rows:
        kind = gripper_kind(r.get("cmd", ""), open_s, close_s) if r.get("kind") in ("send", "waypoint") else None
        if kind:
            gripper.append((r["t_wall"], kind))
    if not samples:
        raise SystemExit(f"{path}: 자세 기록이 없다")
    return {"samples": samples, "gripper": gripper, "source": str(path)}


def record_fake(poses_path: Path, settings: dict, slow: float, seed: int) -> dict:
    """W6 시뮬 pick up 손 자세를 Mirobot 좌표로 바꿔 `slow` 배 느리게, 10/5 실측 간격(43–150 ms, 가운데 91 ms)으로 뽑는다."""
    rows = [json.loads(line) for line in poses_path.read_text(encoding="utf-8").splitlines()]
    meta, steps = rows[0]["meta"], [r for r in rows[1:] if "step" in r]
    ref_q = quat_xyzw_to_wxyz(tuple(meta["start_eef_quat_xyzw"]))
    ref_flange = grip_to_flange(meta["start_eef_pos"], ref_q)

    def to_mirobot(pos, q_xyzw):
        q = quat_xyzw_to_wxyz(tuple(q_xyzw))
        q_m = libero_to_mirobot_quat(q)
        xyz = libero_to_mirobot_flange_mm(grip_to_flange(pos, q), q, q_m, ref_flange, ref_q, settings["point"],
                                          settings["scale"], settings["ref_mirobot_mm"], settings["tool_mm"])
        return list(xyz) + list(quat_to_euler_xyz_deg(q_m))

    sim_t = [0.0] + [r["step"] * DT for r in steps]
    sim_pose = [to_mirobot(meta["start_eef_pos"], meta["start_eef_quat_xyzw"])] + \
               [to_mirobot(r["eef_pos"], r["eef_quat_xyzw"]) for r in steps]
    rng = random.Random(seed)
    end, samples, t = sim_t[-1] * slow, [], 0.0
    while t < end:
        samples.append((t, lerp_at(sim_t, sim_pose, t / slow)))
        t += rng.triangular(0.043, 0.150, 0.091)
    samples.append((end, sim_pose[-1]))
    gripper, sign = [], None
    for r in steps:  # 시뮬 action[6] 부호가 바뀐 스텝 — 그 스텝을 내기 시작한 시각을 늘린다
        now = "close" if r["action"][6] > 0 else "open"
        if now != sign:
            gripper.append(((r["step"] - 1) * DT * slow, now))
            sign = now
    return {"samples": samples, "gripper": gripper, "source": f"fake {poses_path} slow {slow} seed {seed}"}


def lerp_at(ts, values, t):
    i = min(max(bisect.bisect_right(ts, t), 1), len(ts) - 1)
    t0, t1 = ts[i - 1], ts[i]
    w = 0.0 if t1 == t0 else min(max((t - t0) / (t1 - t0), 0.0), 1.0)
    return [a + (b - a) * w for a, b in zip(values[i - 1], values[i])]


# ── 실물 자세 → LIBERO (칸 시각마다) ─────────────────────────────────────

class RealPoses:
    """기록 샘플을 LIBERO 파지점 자세로 바꿔 두고, 임의 시각을 보간한다 — 위치는 선형, 자세는 정규화 선형(nlerp, 부호 맞춤)."""

    def __init__(self, samples, ref_flange, ref_q, settings):
        self.t = [t for t, _ in samples]
        self.poses = [mirobot_to_libero_pose(c[:3], c[3:], ref_flange, ref_q, settings) for _, c in samples]

    def at(self, t):
        i = min(max(bisect.bisect_right(self.t, t), 1), len(self.t) - 1)
        t0, t1 = self.t[i - 1], self.t[i]
        w = 0.0 if t1 == t0 else min(max((t - t0) / (t1 - t0), 0.0), 1.0)
        (p0, q0), (p1, q1) = self.poses[i - 1], self.poses[i]
        if sum(a * b for a, b in zip(q0, q1)) < 0:
            q1 = tuple(-v for v in q1)
        p = [a + (b - a) * w for a, b in zip(p0, p1)]
        q = quat_normalize(tuple(a + (b - a) * w for a, b in zip(q0, q1)))
        return p, q

    def gap_before(self, t):
        """t 를 둘러싼 두 샘플 사이 간격 (s) — 누락 검사용."""
        i = min(max(bisect.bisect_right(self.t, t), 1), len(self.t) - 1)
        return self.t[i] - self.t[i - 1]


def closed_fraction(t, gripper, close_s):
    """B' — 손가락이 얼마나 닫혔나 (0 열림 ~ 1 잡음). 명령 시각부터 close_s 동안 지금 값에서 목표로 직선으로 간다 (임의 판단)."""
    def ramp(start, goal, since, now):
        w = 1.0 if close_s <= 0 else min(max((now - since) / close_s, 0.0), 1.0)
        return start + (goal - start) * w

    value, goal, since = 0.0, 0.0, None
    for tg, kind in gripper:
        if tg > t:
            break
        if since is not None:
            value = ramp(value, goal, since, tg)
        goal, since = (1.0 if kind == "close" else 0.0), tg
    return 0.0 if since is None else ramp(value, goal, since, t)


def gripper_action(t, gripper) -> float:
    """시뮬 그리퍼 action — t 까지 마지막 명령이 close 면 +1, 아니면 −1 (Panda 는 부호만 본다)."""
    grip = -1.0
    for tg, kind in gripper:
        if tg <= t:
            grip = 1.0 if kind == "close" else -1.0
    return grip


def count_noops(actions) -> int:
    count, kept = 0, None
    for a in actions:
        if math.sqrt(sum(v * v for v in a[:6])) < NOOP_THRESHOLD and (kept is None or a[6] == kept[6]):
            count += 1
        else:
            kept = a
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--fake", type=Path, help="W6 손 좌표 기록(panda-poses) → 가짜 실물 기록")
    src.add_argument("--run-gcode-log", type=Path, help="run_gcode 기록 (data/gcode_run/*.jsonl)")
    parser.add_argument("--gcode", type=Path, required=True, help="실물에 보낸 G-code — 변환 설정(머리말)과 출처 손 좌표 기록")
    parser.add_argument("--poses", type=Path, help="장면·Panda 시작 자세를 가져올 손 좌표 기록. 없으면 G-code 머리말 '; 출처'")
    parser.add_argument("--slow", type=float, default=2.34, help="--fake: 실물이 시뮬보다 몇 배 느린가 (10/5 실측 2.34)")
    parser.add_argument("--fake-seed", type=int, default=0, help="--fake: 기록 간격 난수 seed")
    parser.add_argument("--close-s", type=float, default=1.0, help="B' 손가락이 열림→잡음까지 걸리는 시간 (임의 1 s — 손목 영상으로 잴 값)")
    parser.add_argument("--gripper-open-s", type=int, default=40, help="열기 M4 S 값 (W4 기본)")
    parser.add_argument("--gripper-close-s", type=int, default=60, help="닫기 M4 S 값 (W4 기본)")
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--out", type=Path, default=Path("data/follow_record"))
    args = parser.parse_args()

    text = args.gcode.read_text(encoding="utf-8")
    settings = settings_from_gcode(text)
    poses_path = args.poses or args.fake
    if poses_path is None:
        m = SOURCE_RE.search(text)
        if not m:
            raise SystemExit("--poses 가 필요하다 — G-code 머리말에 '; 출처 ….jsonl' 이 없다")
        poses_path = REPO / m.group(1)
    meta = json.loads(poses_path.read_text(encoding="utf-8").splitlines()[0])["meta"]
    ref_q = quat_xyzw_to_wxyz(tuple(meta["start_eef_quat_xyzw"]))
    ref_flange = grip_to_flange(meta["start_eef_pos"], ref_q)

    record = (record_fake(args.fake, settings, args.slow, args.fake_seed) if args.fake
              else record_from_run_gcode(args.run_gcode_log, args.gripper_open_s, args.gripper_close_s))
    t_first = record["samples"][0][0]
    samples = [(t - t_first, c) for t, c in record["samples"]]
    gripper = [(t - t_first, k) for t, k in record["gripper"]]
    real = RealPoses(samples, ref_flange, ref_q, settings)
    k_max = int(samples[-1][0] / DT)

    from preview import create_env  # W6 장면 (LIBERO 를 여기서 불러온다)
    env = create_env(size_mm=meta.get("block_size_mm"), resolution=args.size, cameras=("agentview",),
                     ignore_done=True, task=meta["task"], seed=meta["seed"])
    obs = env.reset()
    target = env.env.objects_dict[env.rgb_task["target_object"]]
    initial_goal = bool(env.check_success())
    rows = []
    t0 = time.time()
    for k in range(k_max + 1):
        t_k = k * DT
        p_sim = [float(v) for v in obs["robot0_eef_pos"]]
        q_sim = quat_xyzw_to_wxyz(tuple(float(v) for v in obs["robot0_eef_quat"]))
        p_real, q_real = real.at(t_k)
        gap_m, gap_deg = pose_gap(p_sim, q_sim, p_real, q_real)
        frac = closed_fraction(t_k, gripper, args.close_s)
        row = {"t": t_k, "agentview": np.flipud(obs["agentview_image"]).copy(),
               "robot_states": robot_states(fingers(frac), p_real, q_real),
               "sim_robot_states": list(obs["robot0_gripper_qpos"]) + p_sim + list(obs["robot0_eef_quat"]),
               "err_mm": gap_m * 1000 * settings["scale"], "err_deg": gap_deg,
               "gripper_cmd": gripper_action(t_k, gripper), "sample_gap": real.gap_before(t_k)}
        grip = row["gripper_cmd"]
        if k == k_max:
            row["action"] = [0.0] * 6 + [grip]  # 마지막 칸 — 다음 자세가 없다. HDF5 에는 넣지 않는다
            rows.append(row)
            break
        p_next, q_next = real.at(t_k + DT)  # 목표는 한 칸 앞
        row["action"] = servo_action(p_sim, q_sim, p_next, q_next, grip)
        rows.append(row)
        obs, _, _, _ = env.step(row["action"])
    success = bool(env.check_success())
    still = bool(env.env._check_grasp(env.env.robots[0].gripper, target))
    env.close()
    rows = rows[:-1]  # 짝 없는 마지막 칸

    err = np.array([r["err_mm"] for r in rows])
    deg = np.array([r["err_deg"] for r in rows])
    actions = np.array([r["action"] for r in rows])
    summary = {"steps": len(rows), "duration_s": round(samples[-1][0], 2),
               "sample_hz": round(len(samples) / samples[-1][0], 2) if samples[-1][0] else None,
               "max_sample_gap_s": round(max(b[0] - a[0] for a, b in zip(samples, samples[1:])), 3),
               "err_mm_mean": round(float(err.mean()), 2), "err_mm_p95": round(float(np.percentile(err, 95)), 2),
               "err_mm_max": round(float(err.max()), 2), "err_deg_max": round(float(deg.max()), 2),
               "noops": count_noops(actions.tolist()), "sim_initial_goal": initial_goal,
               "sim_goal_end": success, "sim_grasp_end": still,
               "sim_success": (not initial_goal) and success and still}

    args.out.mkdir(parents=True, exist_ok=True)
    stem = (Path(record["source"].split()[1]).stem if args.fake else args.run_gcode_log.stem)
    path = args.out / f"{stem}{'-fake' if args.fake else ''}.hdf5"
    with h5py.File(path, "w") as f:
        f.create_dataset("t", data=np.array([r["t"] for r in rows]))
        f.create_dataset("agentview_rgb", data=np.stack([r["agentview"] for r in rows]))
        f.create_dataset("actions", data=actions)
        f.create_dataset("robot_states", data=np.array([r["robot_states"] for r in rows]))
        f.create_dataset("sim_robot_states", data=np.array([r["sim_robot_states"] for r in rows]))
        for key in ("err_mm", "err_deg", "gripper_cmd", "sample_gap"):
            f.create_dataset(key, data=np.array([r[key] for r in rows]))
        f.attrs["meta"] = json.dumps({"record": record["source"], "gcode": str(args.gcode), "poses": str(poses_path),
                                      "task": meta["task"], "seed": meta["seed"], "settings": settings,
                                      "close_s": args.close_s, "dt": DT, "summary": summary,
                                      "gripper_events": gripper}, ensure_ascii=False)
    print(json.dumps(summary, ensure_ascii=False))
    print(f"→ {path} ({path.stat().st_size / 1e6:.0f} MB, {time.time() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
