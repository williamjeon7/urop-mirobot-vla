"""Render one fixed LIBERO state and verify a nominal-FOV image transform.

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
import cv2
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
            assert raw.shape == (height, width, 3) and raw.dtype == np.uint8
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
        # Map the wide render to a centered pinhole target with nominal 84x58 FOV.
        # This is a simulated projection target, not a physical D405 calibration.
        width, height = 1280, 720
        k_source = np.array(centered_intrinsics(width, height, 58.0))
        k_target = k_source.copy()
        k_target[0, 0] = width / (2 * math.tan(math.radians(84.0) / 2))
        transform = k_target @ np.linalg.inv(k_source)
        target_rgb = cv2.warpPerspective(np.asarray(frames[-1]), transform,
                                        (width, height), flags=cv2.INTER_LINEAR)
        target_image = Image.fromarray(target_rgb)
        target_image.save(args.out / "nominal84x58_wide.png")
        coverage = cv2.warpPerspective(np.full((height, width), 255, np.uint8),
                                       transform, (width, height), flags=cv2.INTER_NEAREST)
        assert np.all(coverage == 255), "Target samples outside the source image"
        # Check OpenCV's pixel transform against an independent 3-D point projection.
        points = np.array([[0., 0., 1.], [.1, .05, 1.], [-.3, .2, 1.]])
        source_pixels = (k_source @ points.T).T[:, :2]
        expected_pixels = (k_target @ points.T).T[:, :2]
        transformed_pixels = cv2.perspectiveTransform(source_pixels[:, None, :],
                                                     transform)[:, 0, :]
        max_error = float(np.max(np.linalg.norm(transformed_pixels - expected_pixels, axis=1)))
        assert max_error < 1e-9
        # A channel-order check uses known RGB colors, independent of camera hardware.
        color_samples = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255]]], dtype=np.uint8)
        bgr = cv2.cvtColor(color_samples, cv2.COLOR_RGB2BGR)
        assert np.array_equal(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), color_samples)
        projection_check = {
            "source_case": "nominal58_wide", "output": "nominal84x58_wide.png",
            "target_horizontal_fov_deg": 84.0, "target_vertical_fov_deg": 58.0,
            "K_target_centered_design_px": k_target.tolist(),
            "source_to_target_homography": transform.tolist(),
            "projection_test_points": points.tolist(),
            "max_projection_test_error_px": max_error,
            "source_covers_all_output_pixels": True,
            "rgb_bgr_roundtrip": True,
            "image_format": {"shape": list(target_rgb.shape), "dtype": str(target_rgb.dtype)},
        }
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
        alignment_sheet = Image.new("RGB", (1120, 420), "#edf0f4")
        alignment_draw = ImageDraw.Draw(alignment_sheet)
        for left, title, frame in [(10, "C: simulated H 89.16 / V 58 deg", frames[-1]),
                                   (570, "D: target H 84 / V 58 deg", target_image)]:
            alignment_draw.text((left, 16), title, fill="#14243a", font=font)
            preview = frame.copy()
            preview.thumbnail((540, 304))
            alignment_sheet.paste(preview, (left, 58))
        alignment_draw.text((16, 384), "Both outputs: 1280 x 720. Same camera pose; nominal pinhole target.",
                            fill="#14243a", font=font)
        alignment_sheet.save(args.out / "projection_alignment.png")
        report = {
            "scene": str(args.bddl.resolve()), "seed": 0,
            "versions": {x: importlib.metadata.version(x)
                         for x in ("mujoco", "robosuite", "numpy", "Pillow", "opencv-python")},
            "baseline_cameras": cameras, "renders": rendered,
            "projection_alignment": projection_check,
            "state_unchanged_during_render": True,
            "notes": "Projection comparison only; no D405 measurements or calibration.",
        }
        (args.out / "camera_parameters.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"versions": report["versions"],
                          "camera_fovy": {k: v["fovy_deg"] for k, v in cameras.items()},
                          "renders": rendered, "projection_alignment": projection_check,
                          "state_unchanged": True}, indent=2))
    finally:
        env.close()


if __name__ == "__main__":
    main()
