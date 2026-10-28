"""agentview | eye_in_hand side-by-side MP4 of the W6 red pick up, then a wrist turn.

    conda activate libero
    LIBERO_CONFIG_PATH=docs/W6/.libero python -B docs/W9/panda_cameras/two_view_video.py

The wrist turn rotates the gripper about world z (joint7 does most of it) while holding
the block, so the eye_in_hand view visibly turns with the hand.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "W6" / "rgb_blocks"))

import imageio
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial.transform import Rotation

from pickup import TOP_DOWN, run_pickup
from preview import create_env

RES = 256          # policy input size
SCALE = 2          # upscale for viewing
FPS = 20
TURN_DEG = 60.0    # wrist turn amplitude
TURN_STEPS = 40    # steps per ramp
GAP = 8


def label(img, text, sub=""):
    im = Image.fromarray(img).resize((RES * SCALE, RES * SCALE), Image.NEAREST)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, im.width, 18], fill=(0, 0, 0))
    d.text((6, 3), text, fill=(255, 255, 0))
    if sub:
        d.text((im.width - 7 * len(sub) - 6, 3), sub, fill=(255, 255, 255))
    return np.array(im)


def frame(obs, step, phase, joint7_deg):
    left = label(np.flipud(obs["agentview_image"]), "agentview (fixed)", f"step {step}  {phase}")
    right = label(np.flipud(obs["robot0_eye_in_hand_image"]), "eye_in_hand (on hand)",
                  f"joint7 {joint7_deg:+.0f} deg")
    pad = np.full((left.shape[0], GAP, 3), 255, np.uint8)
    return np.hstack([left, pad, right])


def main():
    env = create_env(resolution=RES, cameras=("agentview", "robot0_eye_in_hand"),
                     ignore_done=True, task="red")
    robot = env.env.robots[0]
    j7 = robot._ref_joint_pos_indexes[6]
    frames = []

    def joint7():
        return float(np.degrees(env.sim.data.qpos[j7]))

    def on_step(obs, step, phase, goal):
        frames.append(frame(obs, step, phase, joint7()))

    try:
        obs = env.reset()
        frames.append(frame(obs, 0, "start", joint7()))
        obs, result = run_pickup(env, obs, env.rgb_task["target_object"], on_step=on_step)
        print("pickup:", result["steps"], "steps, still grasped:", result["still_grasped"])

        # Wrist turn: hold position, ramp the yaw target 0 -> +T -> -T -> 0.
        hold = obs["robot0_eef_pos"].copy()
        step = result["steps"]
        ramp = np.concatenate([np.linspace(0, TURN_DEG, TURN_STEPS),
                               np.linspace(TURN_DEG, -TURN_DEG, 2 * TURN_STEPS),
                               np.linspace(-TURN_DEG, 0, TURN_STEPS),
                               np.zeros(15)])
        j7_seen = []
        for yaw in ramp:
            goal_R = Rotation.from_euler("z", yaw, degrees=True).as_matrix() @ TOP_DOWN
            cur = env.sim.data.site_xmat[robot.eef_site_id].reshape(3, 3)
            action = np.zeros(7, np.float32)
            action[:3] = np.clip((hold - obs["robot0_eef_pos"]) / 0.05, -0.5, 0.5)
            action[3:6] = np.clip(Rotation.from_matrix(goal_R @ cur.T).as_rotvec() / 0.5, -0.5, 0.5)
            action[6] = 1.0
            obs, _, _, _ = env.step(action)
            step += 1
            j7_seen.append(joint7())
            frames.append(frame(obs, step, "wrist turn", j7_seen[-1]))
        print("joint7 range during turn: {:.1f} .. {:.1f} deg".format(min(j7_seen), max(j7_seen)))
    finally:
        env.close()

    out = HERE / "two_view_pickup_red_s0.mp4"
    imageio.mimwrite(out, frames, fps=FPS, codec="libx264", quality=8, macro_block_size=1)
    Image.fromarray(frames[len(frames) - len(ramp) + TURN_STEPS - 1]).save(HERE / "two_view_wrist_turn.png")
    print("wrote", out, len(frames), "frames")


if __name__ == "__main__":
    main()
