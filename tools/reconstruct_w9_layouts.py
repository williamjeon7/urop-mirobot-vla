"""Reconstruct the ten W9 initial layouts in a shared, explicitly local paper frame.

Run with docs/W9/.venv/bin/python. No robot, training or raw metadata writes.
The seed lattice below is specific to these ten visually inspected initial frames.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from docs.W9.d405.capture_storage import resolve_blue_episode
from tools.w9_layout_geometry import (fit_table_pose, paper_to_pixel, pixel_rays,
                                      pixel_to_paper)

W9 = ROOT / 'docs/W9'
REPORT = W9 / 'data/layout_reconstruction'
IMAGES = W9 / 'images/layout_reconstruction'
COLORS = dict(red=(45, 45, 220), green=(50, 155, 40), blue=(220, 110, 25))
SIDE_CM = 2.0
# Approximate location of the same printed 0/top-border intersection, visually
# checked in every frame; these only seed searches for actual dark grid lines.
ORIGIN_SEEDS = [(334, 163), (336, 162), (333, 164), (332, 163), (330, 163),
                (331, 162), (331, 161), (332, 163), (332, 161), (330, 161)]


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False,
                                    allow_nan=False) + '\n', encoding='utf-8')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_image(path, image):
    ok, encoded = cv2.imencode(Path(path).suffix, image)
    if not ok:
        raise OSError(path)
    encoded.tofile(path)


def locate_crossing(response, hsv, seed, search_radius=4):
    u, v = seed
    u0, v0 = round(u), round(v)
    if not (15 < u0 < 625 and 157 < v0 < 470):
        return None
    if hsv[v0-6:v0+7, u0-6:u0+7, 1].max() > 100:
        return None
    crop = response[v0-6:v0+7, u0-6:u0+7]
    xx, yy = crop.mean(axis=0), crop.mean(axis=1)
    lo, hi = 6-search_radius, 7+search_radius
    ix, iy = int(xx[lo:hi].argmax())+lo, int(yy[lo:hi].argmax())+lo
    if xx[ix] < 4 or yy[iy] < 4:
        return None

    def subpixel(profile, k):
        den = profile[k-1] - 2*profile[k] + profile[k+1]
        return .5*(profile[k-1]-profile[k+1])/den if den < -.01 else 0.

    return np.array([u0+ix-6+subpixel(xx, ix), v0+iy-6+subpixel(yy, iy)])


def grid_candidates(image, origin):
    """Measure crossings from two perpendicular dark-line intensity profiles.

    An unchanged initial guess is never treated as a measured corner. Mean
    profiles suppress isolated marks; RANSAC later rejects radial arcs/text.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(float)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    response = cv2.GaussianBlur(gray, (15, 15), 0) - gray
    points, xy, ids = [], [], []
    for row in range(0, 20, 2):
        for col in range(-18, 19, 3):
            u, v = origin[0] - 15.5*col, origin[1] + 15.5*row
            p = locate_crossing(response, hsv, (u, v))
            if p is None or np.linalg.norm(p-[u, v]) > 5:
                continue
            points.append(p)
            xy.append([-row, col])
            ids.append((row//2, (col+18)//3))
    return np.asarray(xy, float), np.asarray(points, float), np.asarray(ids)


def calibrate(image, origin, intrinsics):
    xy, pixels, ids = grid_candidates(image, origin)
    # Reserve by lattice index before robust fitting, not by fitted residual.
    validation = (ids[:, 0] + ids[:, 1]) % 4 == 1
    train = ~validation
    normalized = pixel_rays(pixels, intrinsics)[:, :2]
    cv2.setRNGSeed(20261102)
    _, inliers = cv2.findHomography(xy[train], normalized[train], cv2.RANSAC,
                                   1.25/intrinsics['fx'], maxIters=5000)
    if inliers is None or inliers.sum() < 16:
        raise ValueError('Insufficient actual grid crossings.')
    train_indices = np.flatnonzero(train)[inliers[:, 0].astype(bool)]
    R, t, diag = fit_table_pose(xy[train_indices], pixels[train_indices], intrinsics)
    for _ in range(2):
        errors = np.asarray(diag['reprojection_errors_px'])
        good = errors < 1.5
        if good.all():
            break
        train_indices = train_indices[good]
        R, t, diag = fit_table_pose(xy[train_indices], pixels[train_indices], intrinsics)
    # Localize reserved crossings again around the TRAINING pose's prediction.
    # This removes the rough 15.5px seed lattice's perspective drift. The actual
    # dark-line profile still determines each position; no validation point is
    # used to fit pose, nor discarded on the basis of its reprojection error.
    vi = np.flatnonzero(validation)
    predicted = paper_to_pixel(np.column_stack([xy[vi], np.zeros(len(vi))]),
                               intrinsics, R, t)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(float)
    response = cv2.GaussianBlur(gray, (15, 15), 0)-gray
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    kept, measured, rejected = [], [], []
    for j, prediction in zip(vi, predicted):
        point = locate_crossing(response, hsv, prediction, search_radius=3)
        if point is None:
            rejected.append(dict(paper_xy_cm=xy[j].tolist(), reason='No strong uncolored crossing'))
        else:
            kept.append(j)
            measured.append(point)
    vi, measured = np.asarray(kept), np.asarray(measured)
    if len(vi) < 10:
        raise ValueError('Insufficient reserved grid crossings.')
    predicted = paper_to_pixel(np.column_stack([xy[vi], np.zeros(len(vi))]), intrinsics, R, t)
    residual = np.linalg.norm(predicted-measured, axis=1)
    recovered = pixel_to_paper(measured, intrinsics, R, t)
    error_cm = np.linalg.norm(recovered-xy[vi], axis=1)
    diag.update(validation_count=len(vi), validation_rejected=rejected,
                validation_rms_px=float(np.sqrt(np.mean(residual**2))),
                validation_max_px=float(residual.max()),
                validation_rms_cm=float(np.sqrt(np.mean(error_cm**2))),
                validation_max_cm=float(error_cm.max()),
                validation_note='Reserved before fitting; search initialized by training pose, localized from image intensity. No residual-based validation filtering.',
                controls=[dict(paper_xy_cm=xy[j].tolist(), pixel_uv=pixels[j].tolist())
                          for j in train_indices],
                validation=[dict(paper_xy_cm=xy[j].tolist(), pixel_uv=measured[k].tolist(),
                                 error_px=float(residual[k]), error_cm=float(error_cm[k]))
                            for k, j in enumerate(vi)],
                R_paper_to_camera=R.tolist(), t_paper_to_camera_cm=t.tolist())
    if diag['reprojection_rms_px'] > 1 or diag['validation_rms_px'] > 2:
        raise ValueError(f'Inspect grid fit: {diag["reprojection_rms_px"]}, {diag["validation_rms_px"]}')
    return R, t, diag


def colored_contour(image, color, saturation=None):
    if saturation is None:
        saturation = 20 if color == 'green' else 65
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lo, hi = dict(red=(0, 13), green=(30, 89), blue=(90, 135))[color]
    mask = cv2.inRange(hsv, (lo, saturation, 35), (hi, 255, 255))
    if color == 'red':
        mask |= cv2.inRange(hsv, (170, saturation, 35), (179, 255, 255))
    mask[:185] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    viable = [c for c in contours if 400 < cv2.contourArea(c) < 4000]
    if len(viable) != 1:
        raise ValueError(f'{color}: expected one colored block, got {len(viable)}')
    return viable[0].reshape(-1, 2).astype(float)


def cube_vertices(x, y, yaw, side_cm=SIDE_CM, height_cm=SIDE_CM):
    theta = np.deg2rad(yaw)
    c, s = np.cos(theta), np.sin(theta)
    rotation = np.array([[c, -s], [s, c]])
    square = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]]) * side_cm/2
    square = square @ rotation.T + [x, y]
    return np.column_stack([np.tile(square, (2, 1)), np.repeat([0., height_cm], 4)])


def boundary_samples(polygon, count=6):
    return (polygon[:, None, :]*(1-np.arange(count)/count)[None, :, None]
            + np.roll(polygon, -1, axis=0)[:, None, :]
            * (np.arange(count)/count)[None, :, None]).reshape(-1, 2)


def distances_to_polygon(points, polygon):
    a, b = polygon, np.roll(polygon, -1, axis=0)
    v = b-a
    alpha = np.clip(np.sum((points[:, None]-a)*v, axis=2)/np.sum(v*v, axis=1), 0, 1)
    delta = points[:, None]-a-alpha[:, :, None]*v
    return np.min(np.sum(delta*delta, axis=2), axis=1)


def fit_cube(contour, intrinsics, R, t):
    # Fit all visible colored faces, avoiding the bias of treating silhouette
    # centroid as the center of the top face. Use undistorted virtual pixels.
    rays = pixel_rays(contour, intrinsics)
    scale = np.array([intrinsics['fx'], intrinsics['fy']])
    observed = cv2.convexHull((rays[:, :2]*scale).astype(np.float32)).reshape(-1, 2)
    samples = boundary_samples(observed)
    moments = cv2.moments(contour.astype(np.float32))
    center_pixel = np.array([moments['m10'], moments['m01']])/moments['m00']
    initial = pixel_to_paper(center_pixel, intrinsics, R, t, height_cm=SIDE_CM/2)

    def hull(params):
        camera = cube_vertices(*params) @ R.T + t
        projected = camera[:, :2]/camera[:, 2, None]*scale
        return cv2.convexHull(projected.astype(np.float32)).reshape(-1, 2)

    def loss(params):
        polygon = hull(params)
        return (np.mean(distances_to_polygon(samples, polygon))
                + np.mean(distances_to_polygon(boundary_samples(polygon), observed)))/2

    best, best_loss = None, float('inf')
    for yaw in (0., 30., 60.):
        p = np.r_[initial, yaw]
        value = loss(p)
        for level in range(8):
            steps = np.array([.24, .24, 12.]) / 2**level
            for _ in range(18):
                previous = value
                for axis in range(3):
                    for sign in (-1, 1):
                        candidate = p.copy()
                        candidate[axis] += sign*steps[axis]
                        val = loss(candidate)
                        if val < value:
                            p, value = candidate, val
                if previous-value < 1e-8:
                    break
        if value < best_loss:
            best, best_loss = p, value
    if best_loss > 9:
        raise ValueError(f'Poor 2cm cube silhouette fit: {best_loss**.5:.2f}px')
    x, y, yaw = best
    raw_hull = paper_to_pixel(cube_vertices(x, y, yaw), intrinsics, R, t)
    uncorrected = pixel_to_paper(center_pixel, intrinsics, R, t, height_cm=0)
    return dict(xy_cm=[float(x), float(y)], yaw_mod_90_deg=float(yaw % 90),
                silhouette_rms_virtual_px=float(best_loss**.5),
                observed_contour_uv=contour.tolist(),
                model_vertices_uv=raw_hull.tolist(),
                uncorrected_silhouette_centroid_projection_cm=uncorrected.tolist(),
                correction_from_uncorrected_cm=(best[:2]-uncorrected).tolist())


def label(image, text, xy, color=(245, 245, 245), size=.48):
    cv2.putText(image, text, xy, cv2.FONT_HERSHEY_SIMPLEX, size, (15, 15, 15), 3, cv2.LINE_AA)
    cv2.putText(image, text, xy, cv2.FONT_HERSHEY_SIMPLEX, size, color, 1, cv2.LINE_AA)


def annotate(image, number, intrinsics, R, t, calibration, blocks):
    canvas = image.copy()
    for control in calibration['controls']:
        cv2.circle(canvas, tuple(np.rint(control['pixel_uv']).astype(int)), 2, (160, 100, 220), -1)
    for control in calibration['validation']:
        p = tuple(np.rint(control['pixel_uv']).astype(int))
        cv2.drawMarker(canvas, p, (100, 190, 220), cv2.MARKER_TILTED_CROSS, 5, 1)
    axes = paper_to_pixel(np.array([[0., 0., 0.], [-4., 0., 0.], [0., 4., 0.]]), intrinsics, R, t)
    origin = tuple(np.rint(axes[0]).astype(int))
    cv2.circle(canvas, origin, 5, (0, 255, 255), 2)
    for end, name in zip(axes[1:], ('-X (below border)', '+Y (left)')):
        p = tuple(np.rint(end).astype(int))
        cv2.arrowedLine(canvas, origin, p, (0, 255, 255), 2, tipLength=.13)
        label(canvas, name, (p[0]+5, p[1]-6), size=.38)
    label(canvas, 'O: printed 0 / top grid border', (origin[0]+9, origin[1]-10), size=.38)
    for color, result in blocks.items():
        c = COLORS[color]
        contour = np.rint(result['observed_contour_uv']).astype(np.int32)
        cv2.polylines(canvas, [contour], True, c, 1, cv2.LINE_AA)
        vertices = np.rint(result['model_vertices_uv']).astype(np.int32)
        cv2.polylines(canvas, [vertices[:4]], True, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.polylines(canvas, [vertices[4:]], True, c, 2, cv2.LINE_AA)
        for a, b in zip(vertices[:4], vertices[4:]):
            cv2.line(canvas, tuple(a), tuple(b), c, 1, cv2.LINE_AA)
        center = tuple(np.rint(paper_to_pixel([*result['xy_cm'], 0.], intrinsics, R, t)).astype(int))
        cv2.drawMarker(canvas, center, (255, 255, 255), cv2.MARKER_CROSS, 10, 2)
    # Labels on a separate panel avoid hiding the source blocks/grid.
    panel = np.full((132, 640, 3), 30, np.uint8)
    label(panel, f'layout{number} | estimated PAPER XY (cm) | target BLUE', (12, 24), size=.52)
    for k, (color, result) in enumerate(blocks.items()):
        x, y = result['xy_cm']
        label(panel, f'{color:5s} X={x:+.1f}  Y={y:+.1f}', (12, 48+23*k), COLORS[color], .5)
    label(panel, 'X: up, Y: left. White cross: footprint. No robot-base registration.', (12, 120), size=.38)
    return np.vstack([canvas, panel])


def reconstruct(number):
    episode = resolve_blue_episode(W9/'data/raw', number)
    meta_path = episode / 'metadata.json'
    meta_hash = sha256(meta_path)
    meta = read_json(meta_path)
    rows = [json.loads(s) for s in (episode/'frames.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    first = rows[0]
    frame_path = episode / first['file']
    image = cv2.imdecode(np.fromfile(frame_path, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape[:2] != (480, 640):
        raise ValueError(frame_path)
    intrinsics = meta['intrinsics']
    R, t, calibration = calibrate(image, ORIGIN_SEEDS[number-1], intrinsics)
    blocks = {}
    for color in COLORS:
        result = fit_cube(colored_contour(image, color), intrinsics, R, t)
        thresholds = (20, 25, 35) if color == 'green' else (50, 65, 80)
        sensitivity = []
        for threshold in thresholds:
            alternative = fit_cube(colored_contour(image, color, threshold), intrinsics, R, t)
            sensitivity.append(dict(saturation_min=threshold, xy_cm=alternative['xy_cm'],
                                    displacement_cm=float(np.linalg.norm(
                                        np.array(alternative['xy_cm'])-result['xy_cm'])),
                                    silhouette_rms_virtual_px=alternative['silhouette_rms_virtual_px']))
        result['segmentation'] = dict(
            color_space='OpenCV HSV on original, uncorrected RGB',
            hue_range=dict(red=[[0, 13], [170, 179]], green=[[30, 89]], blue=[[90, 135]])[color],
            saturation_min=20 if color == 'green' else 65, value_min=35,
            threshold_sensitivity=sensitivity,
            max_threshold_displacement_cm=max(s['displacement_cm'] for s in sensitivity))
        blocks[color] = result
    result = dict(
        format='w9-layout/1', target='blue', unit='cm',
        blocks={color: np.round(b['xy_cm'], 1).tolist() for color, b in blocks.items()},
        photo='layout.jpg', photo_type='annotated_initial_wrist_frame_not_new_overhead_photo',
        estimated=True, source='estimated_from_initial_frame',
        source_frame=dict(file=first['file'], sha256=sha256(frame_path), t_s=first['t_s'],
                          frame_index=0, number=first.get('number')),
        source_metadata_sha256=meta_hash,
        coordinate_frame=dict(id='paper_top_border_zero_Xup_Yleft_cm',
            origin='Intersection of top grid border and printed lateral 0 / X centerline',
            positive_x='Along grid toward top of initial image; visible blocks have negative X',
            positive_y='Along grid toward left of initial image; printed ruler increases leftward',
            positive_z='Above paper, right-handed frame', grid_spacing_cm=1.,
            robot_base_registration=None),
        real_success=meta.get('real_success'),
        real_success_review=meta.get('real_success_review'),
        target_review='User confirmed all ten original recordings picked blue; raw color=red retained.',
        reconstruction=dict(method='Per-frame grid pose + 2cm cube fit to all colored silhouette faces',
            block_side_cm=SIDE_CM, block_height_cm=SIDE_CM,
            packages={name: importlib.metadata.version(name)
                      for name in ('numpy', 'opencv-python', 'pyrealsense2')},
            implementation_sha256={str(path.relative_to(ROOT)): sha256(path)
                                   for path in (Path(__file__), ROOT/'tools/w9_layout_geometry.py')},
            dimension_source='docs/W6/MIROBOT_PICKUP.md and docs/W9/CHECKLIST.md: real blocks 20mm',
            intrinsics=intrinsics, calibration=calibration, block_fits=blocks,
            uncertainty=dict(ground_truth_validated=False, reporting_resolution_cm=.1,
                working_tolerance_cm=.5,
                meaning='Planning tolerance, not a measured bound or confidence interval; systematic error can be larger.',
                contributors=['Color boundary blur / shadow / rounded cube edges',
                              'Nominal 2cm cube dimension and flat paper assumptions',
                              'Grid counting, lens calibration and camera pose',
                              'No measured robot-base-to-paper registration'])))
    if sha256(meta_path) != meta_hash:
        raise RuntimeError('Raw metadata changed.')
    return episode, result, annotate(image, number, intrinsics, R, t, calibration, blocks)


def main():
    REPORT.mkdir(parents=True, exist_ok=True)
    IMAGES.mkdir(parents=True, exist_ok=True)
    # Finish and validate all numerical estimates before writing any sidecars.
    results = []
    for number in range(1, 11):
        result = reconstruct(number)
        results.append(result)
        c = result[1]['reconstruction']['calibration']
        print(f'layout{number}: controls={c["control_count"]}, fit={c["reprojection_rms_px"]:.2f}px, '
              f'reserved={c["validation_rms_px"]:.2f}px', flush=True)
    table, overview = [], []
    for number, (episode, layout, annotated) in enumerate(results, 1):
        write_json(episode/'layout.json', layout)
        write_image(episode/'layout.jpg', annotated)
        calibration = layout['reconstruction']['calibration']
        row = dict(video=number, target='blue', real_success=layout['real_success'],
                   grid_fit_rms_px=calibration['reprojection_rms_px'],
                   reserved_grid_rms_px=calibration['validation_rms_px'],
                   reserved_grid_max_cm=calibration['validation_max_cm'])
        for color, values in layout['blocks'].items():
            row[f'{color}_x_cm'], row[f'{color}_y_cm'] = values
        fits = layout['reconstruction']['block_fits'].values()
        row['max_silhouette_rms_virtual_px'] = max(b['silhouette_rms_virtual_px'] for b in fits)
        row['max_threshold_displacement_cm'] = max(b['segmentation']['max_threshold_displacement_cm'] for b in fits)
        row['max_correction_from_plane_cm'] = max(np.linalg.norm(b['correction_from_uncorrected_cm']) for b in fits)
        table.append(row)
        overview.append(cv2.resize(annotated, (480, 459)))
    write_json(REPORT/'summary.json', dict(date='2026-11-02', frame='paper_top_border_zero_Xup_Yleft_cm',
        estimated=True, episodes=table, nominal_block_side_cm=SIDE_CM,
        implementation='tools/reconstruct_w9_layouts.py',
        no_raw_metadata_changes=True, no_training_or_robot_commands=True))
    with (REPORT/'coordinates.csv').open('w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    write_image(IMAGES/'overview.jpg', np.vstack([np.hstack(overview[:5]), np.hstack(overview[5:])]))
    print('Saved 10 layout.json + layout.jpg, summary.json, coordinates.csv, overview.jpg', flush=True)


if __name__ == '__main__':
    main()
