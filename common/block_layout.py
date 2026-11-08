"""Estimate the initial red/green/blue block positions from the wrist RGB at the initial pose.

Paper coordinates (cm), as printed on the mat: x = 세로 (0 at the robot base centre, + away from
the robot, about -9..30), y = 가로 (0 on the centre line, + to the robot's left, -30..30).
The dataset `layout.json` `blocks` frame is the same with x shifted: blocks X = x - 30.

Method (no user input, no robot motion): the D405 colour camera pose relative to the paper was
fitted from the printed grid on 2026-11-02 at the same initial pose (flange X198.67 Y0 Z230.72,
ABC 0). Each colour silhouette is fitted with a 2 cm cube (tools/reconstruct_w9_layouts.fit_cube,
re-implemented here without pyrealsense2), then a constant offset measured on W10 L01-L20
is added. Validation numbers are kept in CALIBRATION["validation"].
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
CALIBRATION_DIR = REPO / "docs/W9/data/calibration/depth_registration_20261102_01"
COLORS = ("red", "green", "blue")
SIDE_CM = 2.0  # nominal cube edge used only to model the silhouette
PAPER_X_SHIFT_CM = 30.0  # paper x (세로) = dataset blocks X + 30
PAPER_RANGE_CM = {"x": (-9.0, 30.0), "y": (-30.0, 30.0)}
INITIAL_POSE = (198.67, 0.0, 230.72, 0.0, 0.0, 0.0)  # flange pose of the calibration snapshot
POSE_TOLERANCE = (2.0, 1.0)  # mm, deg: estimates are only valid at the calibrated pose
CALIBRATION = {
    "camera_pose": "docs/W9/data/calibration/depth_registration_20261102_01/grid_fit.json",
    "intrinsics": "docs/W9/data/calibration/depth_registration_20261102_01/metadata.json color_intrinsics",
    # Mean (measured - fitted) over W10 L01-L20 (60 blocks), dataset frame, cm.
    "offset_cm": [0.795, 0.300],
    "validation": {
        "uncorrected_L01_L20": {"n": 60, "mean_cm": 0.87, "max_cm": 1.16},
        "corrected_leave_one_layout_out_L01_L20": {"n": 60, "mean_cm": 0.20, "p95_cm": 0.35, "max_cm": 0.50},
        "corrected_vs_planned_L21_L30": {"n": 30, "mean_cm": 0.15, "max_cm": 0.29},
        "checked": "2026-11-08",
    },
}


def load_camera():
    intrinsics = json.loads((CALIBRATION_DIR / "metadata.json").read_text())["color_intrinsics"]
    pose = json.loads((CALIBRATION_DIR / "grid_fit.json").read_text())
    return intrinsics, np.asarray(pose["R"], float), np.asarray(pose["t_cm"], float)


def pixel_rays(pixels, intrinsics):
    """librealsense 2.59 rs2_deproject_pixel_to_point at depth 1 (10-step inverse Brown-Conrady)."""
    pixels = np.asarray(pixels, float).reshape(-1, 2)
    x = (pixels[:, 0] - intrinsics["ppx"]) / intrinsics["fx"]
    y = (pixels[:, 1] - intrinsics["ppy"]) / intrinsics["fy"]
    model = str(intrinsics.get("model", "")).removeprefix("distortion.")
    c = intrinsics.get("coeffs", [0.0] * 5)
    if model == "inverse_brown_conrady":
        xo, yo = x, y
        for _ in range(10):
            r2 = x * x + y * y
            icdist = 1 / (1 + ((c[4] * r2 + c[1]) * r2 + c[0]) * r2)
            xq, yq = x / icdist, y / icdist
            dx = 2 * c[2] * xq * yq + c[3] * (r2 + 2 * xq * xq)
            dy = 2 * c[3] * xq * yq + c[2] * (r2 + 2 * yq * yq)
            x, y = (xo - dx) * icdist, (yo - dy) * icdist
    elif model not in ("none", "") and any(abs(v) > 1e-12 for v in c):
        raise ValueError(f"Unsupported distortion model: {model}")
    return np.column_stack([x, y, np.ones_like(x)])


def pixel_to_paper(pixel, intrinsics, R, t, height_cm=0.0):
    ray = pixel_rays(pixel, intrinsics)[0] @ R
    center = -R.T @ t
    return (center + (height_cm - center[2]) / ray[2] * ray)[:2]


def colored_contour(bgr, color):
    """Same thresholds as tools/reconstruct_w9_layouts.colored_contour (one block per colour)."""
    import cv2
    saturation = 20 if color == "green" else 65
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    lo, hi = dict(red=(0, 13), green=(30, 89), blue=(90, 135))[color]
    mask = cv2.inRange(hsv, (lo, saturation, 35), (hi, 255, 255))
    if color == "red":
        mask |= cv2.inRange(hsv, (170, saturation, 35), (179, 255, 255))
    mask[:185] = 0  # gripper fingers in the upper image
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    viable = [c for c in contours if 400 < cv2.contourArea(c) < 4000]
    if len(viable) != 1:
        raise ValueError(f"{color}: expected one block, found {len(viable)}")
    return viable[0].reshape(-1, 2).astype(float)


def _cube(x, y, yaw):
    c, s = np.cos(np.deg2rad(yaw)), np.sin(np.deg2rad(yaw))
    square = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]]) * SIDE_CM / 2 @ np.array([[c, -s], [s, c]]).T + [x, y]
    return np.column_stack([np.tile(square, (2, 1)), np.repeat([0.0, SIDE_CM], 4)])


def _samples(polygon, count=6):
    w = np.arange(count) / count
    return (polygon[:, None] * (1 - w)[None, :, None] + np.roll(polygon, -1, 0)[:, None] * w[None, :, None]).reshape(-1, 2)


def _distance(points, polygon):
    a, v = polygon, np.roll(polygon, -1, 0) - polygon
    alpha = np.clip(np.sum((points[:, None] - a) * v, axis=2) / np.sum(v * v, axis=1), 0, 1)
    delta = points[:, None] - a - alpha[:, :, None] * v
    return np.min(np.sum(delta * delta, axis=2), axis=1)


def fit_cube(contour, intrinsics, R, t):
    """Pose (x, y, yaw) of a 2 cm cube whose projected hull matches the silhouette (dataset frame)."""
    import cv2
    scale = np.array([intrinsics["fx"], intrinsics["fy"]])
    observed = cv2.convexHull((pixel_rays(contour, intrinsics)[:, :2] * scale).astype(np.float32)).reshape(-1, 2)
    samples = _samples(observed)
    m = cv2.moments(contour.astype(np.float32))
    initial = pixel_to_paper([m["m10"] / m["m00"], m["m01"] / m["m00"]], intrinsics, R, t, SIDE_CM / 2)

    def loss(p):
        camera = _cube(*p) @ R.T + t
        hull = cv2.convexHull((camera[:, :2] / camera[:, 2, None] * scale).astype(np.float32)).reshape(-1, 2)
        return (np.mean(_distance(samples, hull)) + np.mean(_distance(_samples(hull), observed))) / 2

    best, best_loss = None, float("inf")
    for yaw in (0.0, 30.0, 60.0):
        p = np.r_[initial, yaw]
        value = loss(p)
        for level in range(8):
            steps = np.array([0.24, 0.24, 12.0]) / 2 ** level
            for _ in range(18):
                previous = value
                for axis in range(3):
                    for sign in (-1, 1):
                        candidate = p.copy()
                        candidate[axis] += sign * steps[axis]
                        v = loss(candidate)
                        if v < value:
                            p, value = candidate, v
                if previous - value < 1e-8:
                    break
        if value < best_loss:
            best, best_loss = p, value
    if best_loss > 9:
        raise ValueError(f"poor cube fit ({best_loss ** 0.5:.1f} px)")
    return best, float(best_loss ** 0.5)


def pose_matches(cart6):
    if cart6 is None or len(cart6) != 6:
        return False
    position = np.linalg.norm(np.subtract(cart6[:3], INITIAL_POSE[:3]))
    angle = max(abs((a - b + 180) % 360 - 180) for a, b in zip(cart6[3:], INITIAL_POSE[3:]))
    return position <= POSE_TOLERANCE[0] and angle <= POSE_TOLERANCE[1]


def estimate_layout(rgb, cart6):
    """Layout document for layout.json; never raises (failures are recorded per colour)."""
    import cv2
    document = dict(unit="cm", source="auto_wrist_camera_initial_pose", estimated=True,
                    paper_frame="mat print: x=세로 (robot base centre 0, + away), y=가로 (centre 0, + left)",
                    paper_xy_cm={c: None for c in COLORS}, blocks={c: None for c in COLORS},
                    blocks_mat_cm={c: None for c in COLORS}, yaw_mod_90_deg={c: None for c in COLORS},
                    fit_rms_px={c: None for c in COLORS}, errors={},
                    estimation=dict(method="2 cm cube silhouette fit + W10 offset", robot_cart6=list(cart6 or []),
                                    **CALIBRATION))
    if not pose_matches(cart6):
        document.update(source="not_measured", estimated=False,
                        errors={"pose": f"robot not at calibrated initial pose {INITIAL_POSE}: {cart6}"})
        return document
    try:
        intrinsics, R, t = load_camera()
    except (OSError, KeyError, ValueError) as error:
        document.update(source="not_measured", estimated=False, errors={"calibration": str(error)})
        return document
    bgr = cv2.cvtColor(np.asarray(rgb, dtype=np.uint8), cv2.COLOR_RGB2BGR)
    for color in COLORS:
        try:
            (x, y, yaw), rms = fit_cube(colored_contour(bgr, color), intrinsics, R, t)
        except ValueError as error:
            document["errors"][color] = str(error)
            continue
        X, Y = x + CALIBRATION["offset_cm"][0], y + CALIBRATION["offset_cm"][1]
        paper = [round(X + PAPER_X_SHIFT_CM, 2), round(Y, 2)]
        document["paper_xy_cm"][color] = paper
        document["blocks"][color] = [round(X, 2), round(Y, 2)]
        document["blocks_mat_cm"][color] = [paper[1], paper[0]]  # dataset order: [가로, 세로]
        document["yaw_mod_90_deg"][color] = round(float(yaw % 90), 1)
        document["fit_rms_px"][color] = round(rms, 2)
        (lo_x, hi_x), (lo_y, hi_y) = PAPER_RANGE_CM["x"], PAPER_RANGE_CM["y"]
        if not (lo_x <= paper[0] <= hi_x and lo_y <= paper[1] <= hi_y):
            document["errors"][color] = f"outside paper range {PAPER_RANGE_CM}: {paper}"
    if all(document["paper_xy_cm"][c] is None for c in COLORS):
        document.update(source="not_measured", estimated=False)
    return document
