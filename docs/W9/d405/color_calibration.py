"""Classic Mini 24-patch calibration: chart corners -> linear-light 3x3 correction.

No colour-science/contrib package is needed. Input is interpreted as sRGB-like
ISP RGB, not sensor RAW. Reference Lab is adapted ICC D50 -> D65 via Bradford.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

D65 = np.array([.95047, 1., 1.08883])
RGB_XYZ = np.array([[.4124564, .3575761, .1804375],
                    [.2126729, .7151522, .0721750], [.0193339, .1191920, .9503041]])
BRADFORD = np.array([[.8951, .2664, -.1614], [-.7502, 1.7135, .0367], [.0389, -.0685, 1.0296]])


def decode_srgb(rgb):
    rgb = np.asarray(rgb, dtype=np.float64)/255
    return np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4)


def encode_srgb(linear):
    linear = np.clip(linear, 0, 1)
    return np.rint(255*np.where(linear <= .0031308, 12.92*linear, 1.055*linear**(1/2.4)-.055)).astype(np.uint8)


def adapt_xyz(xyz, source, target):
    matrix = np.linalg.inv(BRADFORD) @ np.diag((BRADFORD@target)/(BRADFORD@source)) @ BRADFORD
    return np.asarray(xyz)@matrix.T


def lab_to_xyz(lab, white):
    lab = np.asarray(lab, float)
    fy = (lab[:, 0]+16)/116
    f = np.stack([fy+lab[:, 1]/500, fy, fy-lab[:, 2]/200], axis=-1)
    d = 6/29
    return np.where(f > d, f**3, 3*d*d*(f-4/29))*white


def xyz_to_lab(xyz, white):
    xyz = np.asarray(xyz)/white
    d = 6/29
    f = np.where(xyz > d**3, np.cbrt(xyz), xyz/(3*d*d)+4/29)
    return np.stack([116*f[:, 1]-16, 500*(f[:, 0]-f[:, 1]), 200*(f[:, 1]-f[:, 2])], axis=-1)


def linear_to_lab(rgb, white):
    xyz = np.clip(rgb, 0, 1)@RGB_XYZ.T
    return xyz_to_lab(adapt_xyz(xyz, D65, white), white)


def load_profile(path):
    profile = json.loads(Path(path).read_text(encoding='utf-8'))
    matrix = np.asarray(profile['matrix'], float)
    if profile.get('format') != 'w9-color/1' or matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError('Invalid W9 colour profile.')
    return profile


def apply_rgb(rgb, profile):
    if profile is None:
        return rgb
    return encode_srgb(decode_srgb(rgb)@np.asarray(profile['matrix']))


def pick_corners(image):
    points = []
    # Show at original resolution to make the saved pixel coordinates unambiguous.
    def click(event, x, y, flags, userdata):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append([x, y])
    title = 'Patch GRID corners: TL -> TR -> BR -> BL | Enter accept | r reset | Esc cancel'
    cv2.namedWindow(title)
    cv2.setMouseCallback(title, click)
    try:
        while True:
            view = image.copy()
            for i, point in enumerate(points):
                cv2.circle(view, tuple(point), 5, (0, 255, 0), -1)
                cv2.putText(view, str(i+1), tuple(point), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 255, 255), 2)
            cv2.imshow(title, view)
            key = cv2.waitKey(20) & 0xff
            if key in (10, 13) and len(points) == 4:
                return points
            if key == ord('r'):
                points.clear()
            if key == 27:
                raise KeyboardInterrupt('Corner selection cancelled.')
    finally:
        cv2.destroyAllWindows()


def sample_patches(image_rgb, corners):
    corners = np.asarray(corners, np.float32)
    if corners.shape != (4, 2) or not cv2.isContourConvex(corners.astype(np.int32)):
        raise ValueError('Four convex grid corners must be in TL,TR,BR,BL order.')
    if abs(cv2.contourArea(corners)) < 5000:
        raise ValueError('Chart is too small in the image; move it closer or increase resolution.')
    h, w = image_rgb.shape[:2]
    if np.any(corners < 0) or np.any(corners[:, 0] >= w) or np.any(corners[:, 1] >= h):
        raise ValueError('Chart corner outside image.')
    matrix = cv2.getPerspectiveTransform(corners, np.float32([[0, 0], [600, 0], [600, 400], [0, 400]]))
    flat = cv2.warpPerspective(image_rgb, matrix, (600, 400))
    values, clipping = [], []
    for row in range(4):
        for col in range(6):
            patch = flat[row*100+30:row*100+70, col*100+30:col*100+70]
            values.append(np.median(patch.reshape(-1, 3), axis=0))
            clipping.append(float(np.any((patch <= 1) | (patch >= 254), axis=2).mean()))
    if max(clipping) > .02:
        raise ValueError('Chart patch clips >2% of pixels. Lower exposure / remove glare and recapture.')
    return np.asarray(values), flat


def fit_matrix(measured_rgb, reference_lab, white):
    measured = decode_srgb(measured_rgb)
    target = adapt_xyz(lab_to_xyz(reference_lab, white), white, D65)@np.linalg.inv(RGB_XYZ).T
    if np.linalg.matrix_rank(measured) < 3 or np.linalg.cond(measured) > 100:
        raise ValueError('Ill-conditioned chart samples; verify patch order and lighting.')
    # Six fixed held-out patches cover skin, blue, green, cyan and neutral tones.
    holdout = np.array([0, 7, 13, 17, 20, 22])
    train = np.array([i for i in range(24) if i not in holdout])
    matrix, _, _, _ = np.linalg.lstsq(measured[train], target[train], rcond=None)
    before = np.linalg.norm(linear_to_lab(measured, white)-reference_lab, axis=1)
    after = np.linalg.norm(linear_to_lab(measured@matrix, white)-reference_lab, axis=1)
    report = dict(deltaE_metric='CIE76, ICC D50; not CIEDE2000', train_patch_indices=(train+1).tolist(),
                  heldout_patch_indices=(holdout+1).tolist(),
                  heldout_mean_before=float(before[holdout].mean()), heldout_mean_after=float(after[holdout].mean()),
                  all_mean_before=float(before.mean()), all_mean_after=float(after.mean()),
                  deltaE76_before=before.tolist(), deltaE76_after=after.tolist())
    if report['heldout_mean_after'] >= report['heldout_mean_before']:
        raise ValueError('Held-out patch error did not improve; check orientation, lighting, edition and exposure.')
    return matrix, report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='mode', required=True)
    fit = sub.add_parser('fit')
    fit.add_argument('--image', type=Path, required=True)
    fit.add_argument('--out', type=Path, required=True)
    fit.add_argument('--reference', type=Path, default=Path(__file__).with_name('classic_reference.json'))
    fit.add_argument('--corners', type=Path, help='Optional JSON [[x,y],...] for noninteractive use')
    fit.add_argument('--camera-metadata', type=Path, required=True, help='metadata.json from the chart capture')
    fit.add_argument('--confirm-edition', action='store_true', help='Confirm November 2014+ Classic 24 chart')
    apply = sub.add_parser('apply')
    apply.add_argument('--image', type=Path, required=True)
    apply.add_argument('--profile', type=Path, required=True)
    apply.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if (a.mode == 'fit' and a.corners is None and sys.platform.startswith('linux')
            and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))):
        p.error('No GUI display. Supply --corners path/to/corners.json over headless SSH.')
    image = cv2.imread(str(a.image))
    if image is None:
        raise ValueError('Input image is unreadable.')
    if a.out.exists():
        raise FileExistsError(a.out)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    if a.mode == 'apply':
        corrected = apply_rgb(rgb, load_profile(a.profile))
        if not cv2.imwrite(str(a.out), cv2.cvtColor(corrected, cv2.COLOR_RGB2BGR)):
            raise OSError('Corrected image write failed.')
        return
    if not a.confirm_edition:
        p.error('Confirm chart edition against the reference, then add --confirm-edition.')
    corners = json.loads(a.corners.read_text()) if a.corners else pick_corners(image)
    samples, flat = sample_patches(rgb, corners)
    reference = json.loads(a.reference.read_text(encoding='utf-8'))
    lab = np.asarray(reference['patches_lab_row_major'], float)
    if lab.shape != (24, 3):
        raise ValueError('Need 24 row-major reference Lab values.')
    matrix, report = fit_matrix(samples, lab, np.array(reference['lab_white_xyz']))
    camera = json.loads(a.camera_metadata.read_text(encoding='utf-8'))
    profile = dict(format='w9-color/1', method='linearized sRGB row-vector @ 3x3 matrix',
                   matrix=matrix.tolist(), reference=reference, corners=corners, measured_rgb=samples.tolist(),
                   camera_serial=camera['serial'], camera_options=camera['locked_camera_options'],
                   width=camera['width'], height=camera['height'], fps=camera['fps'],
                   image_sha256=hashlib.sha256(a.image.read_bytes()).hexdigest(), report=report)
    a.out.write_text(json.dumps(profile, indent=2), encoding='utf-8')
    cv2.imwrite(str(a.out.with_suffix('.patches.png')), cv2.cvtColor(flat, cv2.COLOR_RGB2BGR))
    comparison = np.hstack([rgb, apply_rgb(rgb, profile)])
    cv2.imwrite(str(a.out.with_suffix('.comparison.png')), cv2.cvtColor(comparison, cv2.COLOR_RGB2BGR))
    print(json.dumps(report, indent=2))
    print('Saved profile and raw|corrected comparison:', a.out)


if __name__ == '__main__':
    main()
