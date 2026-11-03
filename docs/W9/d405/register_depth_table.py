"""Fit the visible fixed paper grid to a native RGB-D calibration snapshot.

This reuses the inspected W9 grid detector (640x480, approximately 15.5px/cm).
Depth supplies the metric plane; grid intersections supply the paper origin/axes.
No robot-to-table registration is inferred by this module.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from .capture_storage import read_image


def rigid_fit(source, destination):
    source, destination = np.asarray(source, float), np.asarray(destination, float)
    if source.shape != destination.shape or source.ndim != 2 or source.shape[1] != 3 or len(source) < 3:
        raise ValueError('Need at least three paired 3D points.')
    if not np.isfinite(source).all() or not np.isfinite(destination).all():
        raise ValueError('Non-finite registration points.')
    if (np.linalg.matrix_rank(source-source.mean(0)) < 2 or
            np.linalg.matrix_rank(destination-destination.mean(0)) < 2):
        raise ValueError('Registration points are collinear.')
    u, _, vt = np.linalg.svd((source-source.mean(0)).T@(destination-destination.mean(0)))
    rotation = vt.T@u.T
    if np.linalg.det(rotation) < 0:
        vt[-1] *= -1
        rotation = vt.T@u.T
    return rotation, destination.mean(0)-rotation@source.mean(0)


def fit_plane(points, threshold_m=.002):
    points = np.asarray(points, float)
    if len(points) < 100:
        raise ValueError('Too few valid native-depth points on the paper.')
    rng = np.random.default_rng(20261102)
    best = None
    for _ in range(100):
        a, b, c = points[rng.choice(len(points), 3, replace=False)]
        n = np.cross(b-a, c-a)
        if np.linalg.norm(n) < 1e-8:
            continue
        n /= np.linalg.norm(n)
        keep = abs((points-a)@n) < threshold_m
        if best is None or keep.sum() > best.sum():
            best = keep
    if best is None or best.mean() < .6:
        raise ValueError('No dominant paper plane in the fixed paper ROI.')
    for _ in range(3):
        centre = points[best].mean(0)
        _, _, vt = np.linalg.svd(points[best]-centre, full_matrices=False)
        normal = vt[-1]
        best = abs((points-centre)@normal) < threshold_m
    return centre, normal, best


def register(snapshot, origin=(333, 160)):
    from tools.reconstruct_w9_layouts import calibrate
    from tools.w9_layout_geometry import pixel_rays
    snapshot = Path(snapshot)
    meta = json.loads((snapshot/'metadata.json').read_text(encoding='utf-8'))
    if not meta.get('complete'):
        raise ValueError('Incomplete depth snapshot.')
    image = read_image(snapshot/'color.png')
    _, _, grid = calibrate(image, origin, meta['color_intrinsics'])
    depth = np.load(snapshot/meta['depth_stack'], allow_pickle=False)
    intr = meta['depth_intrinsics']
    # This device's native depth stream has zero distortion. Refuse other models
    # here instead of using pinhole deprojection for a distorted stream.
    if any(abs(c) > 1e-12 for c in intr['coeffs']):
        raise ValueError('Nonzero depth distortion needs SDK deprojection.')
    samples = depth[:, 180:455:3, 35:610:3]
    mask = np.count_nonzero(samples, axis=0) >= max(5, int(.8*len(depth)))
    # Discard invalid values before a true valid-only median per selected pixel.
    yy, xx = np.mgrid[180:455:3, 35:610:3]
    zz = np.array([np.median(samples[:, r, c][samples[:, r, c] > 0])
                   for r, c in zip(*np.nonzero(mask))])*meta['depth_scale_m_per_unit']
    u, v = xx[mask], yy[mask]
    points = np.c_[(u-intr['ppx'])/intr['fx']*zz, (v-intr['ppy'])/intr['fy']*zz, zz]
    centre, normal, keep = fit_plane(points)
    transform = meta['factory_depth_to_color']
    r_dc = np.array(transform['rotation']).reshape(3, 3, order='F')
    t_dc = np.array(transform['translation_m'])
    centre_c, normal_c = r_dc@centre+t_dc, r_dc@normal

    def observed(records):
        rays = pixel_rays([r['pixel_uv'] for r in records], meta['color_intrinsics'])
        denominators = rays@normal_c
        if np.any(abs(denominators) < .1):
            raise ValueError('Grid viewing rays are nearly parallel to paper.')
        xyz_c = rays*((centre_c@normal_c)/denominators)[:, None]
        xyz_d = (xyz_c-t_dc)@r_dc
        xyz_t = np.c_[np.array([r['paper_xy_cm'] for r in records])*.01, np.zeros(len(records))]
        return xyz_t, xyz_d

    source, measured = observed(grid['controls'])
    rotation, translation = rigid_fit(source, measured)
    check_t, check_d = observed(grid['validation'])
    errors = np.linalg.norm(check_t@rotation.T+translation-check_d, axis=1)*1000
    plane_error = (points[keep]-centre)@normal*1000
    # Estimate metric scale discrepancy for diagnostics only; never insert scale
    # into a rigid table/camera transform.
    pred = source@rotation.T+translation
    scale = float(np.sum((pred-pred.mean(0))*(measured-measured.mean(0)))/
                  np.sum((pred-pred.mean(0))**2))
    matrix = np.eye(4)
    matrix[:3, :3], matrix[:3, 3] = rotation, translation
    return dict(format='w9-depth-paper-registration/1', snapshot=str(snapshot), unit='m',
                direction='p_C_depth = R_C_depth_from_T * p_T + t_C_depth_from_T',
                T_C_depth_from_T=matrix.tolist(), T_T_from_C_depth=np.linalg.inv(matrix).tolist(),
                paper_origin_definition='top boundary / printed-0 centreline',
                paper_axes='X initial image up, Y left, Z paper-normal up',
                fitted_grid_points=len(source), heldout_grid_points=len(check_t),
                depth_plane_points=int(keep.sum()), depth_plane_inlier_fraction=float(keep.mean()),
                depth_plane_rms_mm=float(np.sqrt(np.mean(plane_error**2))),
                heldout_grid_rms_mm=float(np.sqrt(np.mean(errors**2))),
                heldout_grid_max_mm=float(errors.max()), apparent_metric_scale=scale,
                rgb_grid_validation_rms_mm=grid['validation_rms_cm']*10,
                coordinate_source='measured native depth plane + detected printed grid, 1cm nominal spacing',
                limitation='Grid checks do not independently validate actual printed spacing or robot coordinates.',
                robot_registration=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--origin', nargs=2, type=float, default=[333, 160], metavar=('U', 'V'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    result = register(args.snapshot, args.origin)
    with args.out.open('x', encoding='utf-8') as output:
        json.dump(result, output, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if not k.startswith('T_')}, indent=2))


if __name__ == '__main__':
    main()
