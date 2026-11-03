"""정책 실행 입출력 오프라인 검사 — 녹화 에피소드로, 로봇·GPU 없이 (W10, docs/W10/POLICY_RUN.md 2절).

실행 루프가 쓸 계산(`tools/policy_obs.py`, `common/policy_io.py`)이 학습 데이터와 맞는지 잰다.

1. 영상 — 녹화 PNG → `wrist_from_rgb` 가 HDF5 `eye_in_hand_rgb` 와 같은가
2. proprio — 실행 때처럼 **그 시각 직전의 `?` 응답 하나**로 만든 9칸이 HDF5 `robot_states`(보간값)와 얼마나 다른가
3. 역변환 — LIBERO 자세 → Mirobot X Y Z A B C 가 녹화된 `?` 값으로 돌아오는가
4. action → 목표 — 학습 action 을 **실물** 현재 자세에 더한 목표(`apply_action`)가 실제 다음 자세와 얼마나 다른가.
   라벨은 시뮬 Panda 현재 자세 기준이라 그 차이(따라가기 늦음)만큼 어긋난다
5. 라벨 크기 — 지금 라벨(시뮬 기준) vs 실물 자세 차이로 만든 라벨, LIBERO 통계

    cosmos-policy/.venv/bin/python -m tools.check_policy_io            # 옛 파랑 10개 (layoutblue1–10)
    cosmos-policy/.venv/bin/python -m tools.check_policy_io --episodes 영상11 영상12 --hdf5-dir <dir>

에피소드는 번호(1–10, `capture_storage.resolve_blue_episode` 로 layoutblueN 또는 옛 이름 영상N)나 폴더 이름으로 준다.
HDF5 는 `export_real_hdf5.episode_id`(layoutblueN → videoN) 로 찾는다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import numpy as np

from common.policy_io import apply_action
from common.servo import pose_gap, servo_action
from docs.W9.d405.capture_storage import resolve_blue_episode
from docs.W9.d405.color_calibration import load_profile
from docs.W9.d405.export_real_hdf5 import episode_id
from docs.W9.d405.prepare import read_jsonl
from tools.policy_obs import MirobotFrame, latest_closure, read_rgb, wrist_from_rgb

REPO = Path(__file__).resolve().parents[1]


def stats(values) -> dict:
    v = np.asarray(values, float)
    return dict(mean=float(v.mean()), p95=float(np.percentile(v, 95)), max=float(v.max()))


def check_episode(ep: Path, hdf5: Path, image_every: int) -> dict:
    meta = json.loads((ep / "metadata.json").read_text(encoding="utf-8"))
    frames = read_jsonl(ep / "frames.jsonl")
    events = read_jsonl(ep / "robot.jsonl")
    states = [r for r in events if r["kind"] == "state"]
    st = np.array([r["t_s"] for r in states])
    cart = np.array([r["cart"][:6] for r in states], float)
    profile = load_profile(ep / "color_profile.json")
    frame = MirobotFrame.from_files(ep / "reference.jsonl", ep / "source.gcode")
    mm = 1000.0 * frame.settings["scale"]  # LIBERO m → Mirobot mm (배율 환산)
    with np.load(ep / "aligned.npz", allow_pickle=False) as z:
        aligned = {k: z[k] for k in z.files}
    times, pos, quat = aligned["times"], aligned["positions"], aligned["quaternions_wxyz"]
    with h5py.File(hdf5, "r") as f:
        demo = f["data/demo_0"]
        actions = demo["actions"][:]
        rs = demo["robot_states"][:]
        follow = demo["follow_error_mm_deg"][:]
        images = demo["obs/eye_in_hand_rgb"]
        n = len(actions)
        # 1. 영상
        img_diff, img_checked = 0, 0
        for k in range(0, n, image_every):
            idx = int(aligned["frame_indices"][k])
            mine = wrist_from_rgb(read_rgb(ep / frames[idx]["file"]), profile)
            img_diff = max(img_diff, int(np.abs(mine.astype(int) - images[k].astype(int)).max()))
            img_checked += 1
    grip = dict(duration_s=meta["gripper_seconds"], initial_s=meta["initial_s"], open_s=meta["open_s"],
                closed_s=meta["closed_s"])
    # 2. proprio — 직전 `?` 응답 하나
    age, p_err, f_err = [], [], []
    for k in range(n):
        j = int(np.searchsorted(st, times[k], side="right")) - 1
        mine = frame.proprio(cart[j], latest_closure(events, times[k], **grip))
        age.append((times[k] - st[j]) * 1000)
        p_err.append(np.linalg.norm(mine[2:5] - rs[k, 2:5]) * mm)
        f_err.append(abs(mine[0] - rs[k, 0]))
    # 3. 역변환 — LIBERO → Mirobot, 녹화 `?` 값(같은 시각으로 보간)과 비교
    rt_mm, rt_deg = [], []
    for k in range(n + 1):
        xyz, abc = frame.to_mirobot(pos[k], tuple(quat[k]))
        ref = [np.interp(times[k], st, cart[:, i]) for i in range(6)]
        rt_mm.append(np.linalg.norm(np.subtract(xyz, ref[:3])))
        rt_deg.append(float(np.max(np.abs(np.subtract(abc, ref[3:])))))
    # 4·5. action → 목표, 라벨 크기
    a_mm, a_deg, step_mm, real_labels = [], [], [], []
    for k in range(n):
        q0, q1 = tuple(quat[k]), tuple(quat[k + 1])
        tp, tq = apply_action(pos[k], q0, actions[k])
        dp, dq = pose_gap(tp, tq, pos[k + 1], q1)
        a_mm.append(dp * mm)
        a_deg.append(dq)
        step_mm.append(np.linalg.norm(pos[k + 1] - pos[k]) * mm)
        real_labels.append(servo_action(pos[k], q0, pos[k + 1], q1, float(actions[k][6])))
    real_labels = np.asarray(real_labels)
    moving = np.asarray(step_mm) > 0.5  # 한 칸(0.05 s)에 0.5 mm 넘게 움직인 칸
    # 4-2. 묶음 16개를 묶음 첫 자세에서 차례로 더해 갈 때(중간 자세를 다시 재지 않음) 16번째 목표의 어긋남
    chunk = 16
    acc_sim, acc_real = [], []
    for k in range(n - chunk + 1):
        ps, qs = pos[k], tuple(quat[k])
        pr, qr = pos[k], tuple(quat[k])
        for j in range(chunk):
            ps, qs = apply_action(ps, qs, actions[k + j])
            pr, qr = apply_action(pr, qr, real_labels[k + j])
        acc_sim.append(pose_gap(ps, qs, pos[k + chunk], tuple(quat[k + chunk]))[0] * mm)
        acc_real.append(pose_gap(pr, qr, pos[k + chunk], tuple(quat[k + chunk]))[0] * mm)
    return dict(
        episode=ep.name, steps=n,
        image=dict(checked=img_checked, max_abs_diff=img_diff),
        proprio=dict(state_age_ms=stats(age), position_mm=stats(p_err), finger_m_max=float(max(f_err))),
        roundtrip=dict(position_mm_max=float(max(rt_mm)), abc_deg_max=float(max(rt_deg))),
        action_on_real=dict(position_mm=stats(a_mm), rotation_deg=stats(a_deg),
                            position_mm_moving=stats(np.asarray(a_mm)[moving]),
                            sim_follow_gap_mm=stats(follow[:, 0]),
                            chunk16_open_loop_mm=stats(acc_sim), chunk16_open_loop_real_labels_mm=stats(acc_real)),
        motion=dict(step_mm=stats(step_mm), moving_fraction=float(moving.mean())),
        labels=dict(sim_pos_abs=stats(np.abs(actions[:, :3])), real_pos_abs=stats(np.abs(real_labels[:, :3])),
                    sim_rot_abs=stats(np.abs(actions[:, 3:6])), real_rot_abs=stats(np.abs(real_labels[:, 3:6])),
                    sim_clipped_fraction=float((np.abs(actions[:, :6]) >= 0.999).any(axis=1).mean())),
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--raw-dir", type=Path, default=REPO / "docs/W9/data/raw")
    p.add_argument("--hdf5-dir", type=Path, default=REPO / "data/hdf5_mix/mirobot_real")
    p.add_argument("--episodes", nargs="+", default=[str(i) for i in range(1, 11)],
                   help="번호 1–10 (옛 파랑) 또는 녹화 폴더 이름")
    p.add_argument("--image-every", type=int, default=1, help="영상 비교 간격(칸)")
    p.add_argument("--report", type=Path, default=REPO / "docs/W10/data/policy_io_check.json")
    a = p.parse_args()
    results = []
    for name in a.episodes:
        ep = resolve_blue_episode(a.raw_dir, int(name)) if name.isdigit() else a.raw_dir / name
        hdf5 = next(a.hdf5_dir.glob(f"MIROBOT_{episode_id(ep)}_*.hdf5"))
        r = check_episode(ep, hdf5, a.image_every)
        results.append(r)
        ar = r["action_on_real"]
        print(f"{ep.name:<13} 영상차 {r['image']['max_abs_diff']}  proprio {r['proprio']['position_mm']['max']:.2f} mm"
              f" (응답 나이 최대 {r['proprio']['state_age_ms']['max']:.0f} ms)  역변환 {r['roundtrip']['position_mm_max']:.4f} mm"
              f"  action→목표 평균 {ar['position_mm']['mean']:.2f} · 최대 {ar['position_mm']['max']:.2f} mm,"
              f" {ar['rotation_deg']['max']:.2f}°  (시뮬 늦음 평균 {ar['sim_follow_gap_mm']['mean']:.2f} mm)"
              f"  묶음16 누적 평균 {ar['chunk16_open_loop_mm']['mean']:.1f} · 최대 {ar['chunk16_open_loop_mm']['max']:.1f} mm")
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"report → {a.report}")


if __name__ == "__main__":
    main()
