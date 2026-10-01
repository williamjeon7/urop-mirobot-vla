"""Render one fixed LIBERO state with three camera projections.

Uses the existing W5 LIBERO installation. No policy inference or robot command.
The 58-degree images are nominal D405-like projections, not D405 photographs.
"""

import argparse
import importlib.metadata
import json
import logging
import math
import os
from pathlib import Path

ASSET_DIR = Path(__file__).resolve().parent
W5_DIR = ASSET_DIR.parent

if os.name == "nt":
    os.environ.setdefault("MUJOCO_GL", "wgl")
    os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
    # robosuite 1.4.0 hardcodes a Linux log destination.
    _original_file_handler = logging.FileHandler

    def _windows_file_handler(filename, *args, **kwargs):
        if str(filename) == "/tmp/robosuite.log":
            filename = str(ASSET_DIR / "robosuite.log")
        return _original_file_handler(filename, *args, **kwargs)

    logging.FileHandler = _windows_file_handler

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from libero.libero.envs import OffScreenRenderEnv


def centered_intrinsics(width, height, vertical_fov):
    focal = height / (2.0 * math.tan(math.radians(vertical_fov) / 2.0))
    return [[focal, 0.0, width / 2.0],
            [0.0, focal, height / 2.0], [0.0, 0.0, 1.0]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bddl", type=Path, default=ASSET_DIR / "comparison_scene.bddl")
    parser.add_argument("--out", type=Path, default=ASSET_DIR)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    env = OffScreenRenderEnv(bddl_file_name=str(args.bddl.resolve()),
                             camera_names=["agentview", "robot0_eye_in_hand"],
                             camera_heights=512, camera_widths=512,
                             initialization_noise=None)
    try:
        env.seed(0)
        env.reset()
        sim = env.env.sim
        names = ("agentview", "robot0_eye_in_hand")
        cameras = {}
        for name in names:
            cid = sim.model.camera_name2id(name)
            cameras[name] = {
                "fovy_deg": float(sim.model.cam_fovy[cid]),
                "local_position_m": sim.model.cam_pos[cid].tolist(),
                "local_quaternion_wxyz": sim.model.cam_quat[cid].tolist(),
                "world_position_m": sim.data.cam_xpos[cid].tolist(),
                "world_rotation_matrix": sim.data.cam_xmat[cid].reshape(3, 3).tolist(),
            }
        cid = sim.model.camera_name2id("agentview")
        baseline_fovy = float(sim.model.cam_fovy[cid])
        fixed_qpos = sim.data.qpos.copy()
        frames = []
        rendered = []
        cases = [("baseline_square", 512, 512, baseline_fovy),
                 ("nominal58_square", 512, 512, 58.0),
                 ("nominal58_wide", 1280, 720, 58.0)]
        for label, width, height, fovy in cases:
            sim.model.cam_fovy[cid] = fovy
            raw = sim.render(width=width, height=height, camera_name="agentview")
            # Direct MuJoCo OpenGL output has a bottom-left image origin.
            image = Image.fromarray(np.ascontiguousarray(raw[::-1]))
            image.save(args.out / (label + ".png"))
            assert np.array_equal(sim.data.qpos, fixed_qpos), "Scene state changed"
            hfov = math.degrees(2 * math.atan(width / height *
                                            math.tan(math.radians(fovy) / 2)))
            rendered.append({"case": label, "width": width, "height": height,
                             "fovy_deg": fovy, "horizontal_fov_deg": hfov,
                             "K_centered_approx_px": centered_intrinsics(width, height, fovy)})
            frames.append(image)
        sim.model.cam_fovy[cid] = baseline_fovy
        # A labeled contact sheet for Markdown preview in both VS Code and GitHub.
        sheet = Image.new("RGB", (1100, 440), "#edf0f4")
        draw = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.truetype("arial.ttf" if os.name == "nt" else "DejaVuSans.ttf", 20)
        except OSError:
            font = ImageFont.load_default()
        panel_specs = [(10, "A: baseline {:.0f} deg / 1:1".format(baseline_fovy)),
                       (300, "B: nominal 58 deg / 1:1"),
                       (590, "C: nominal 58 deg / 16:9")]
        for idx, (left, title) in enumerate(panel_specs):
            draw.text((left, 16), title, fill="#14243a", font=font)
            frame = frames[idx].copy()
            frame.thumbnail((498 if idx == 2 else 280, 280))
            sheet.paste(frame, (left, 58))
        draw.text((16, 364), "Same LIBERO state and display height; camera pose and lighting unchanged.",
                  fill="#14243a", font=font)
        draw.text((16, 400), "58 deg is a nominal approximation. These are simulation images.",
                  fill="#14243a", font=font)
        sheet.save(args.out / "camera_comparison.png")
        report = {
            "scene": str(args.bddl.resolve()), "seed": 0,
            "versions": {x: importlib.metadata.version(x)
                         for x in ("mujoco", "robosuite", "numpy", "Pillow")},
            "baseline_cameras": cameras, "renders": rendered,
            "state_unchanged_during_render": True,
            "notes": "Projection comparison only; no D405 measurements or calibration.",
        }
        (args.out / "camera_parameters.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"versions": report["versions"],
                          "camera_fovy": {k: v["fovy_deg"] for k, v in cameras.items()},
                          "renders": rendered, "state_unchanged": True}, indent=2))
    finally:
        env.close()


if __name__ == "__main__":
    main()
