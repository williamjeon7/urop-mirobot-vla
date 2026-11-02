"""Paper-plane geometry for post-hoc W9 layouts, using RealSense RGB intrinsics.

Coordinates are centimetres in a right-handed paper frame: +X is toward the
initial image's top, +Y toward its left, and +Z above the paper. R and t map
paper coordinates to the camera: camera_xyz_cm = R @ paper_xyz_cm + t.

RealSense's inverse_brown_conrady coefficients are interpreted by the actual
SDK, rather than passed to OpenCV as ordinary Brown distortion coefficients.
No device connection is needed for these SDK geometry functions.
"""
from __future__ import annotations

import cv2
import numpy as np


def _sdk_intrinsics(intrinsics):
    """Accept either the saved metadata dictionary or an SDK intrinsics object."""
    import pyrealsense2 as rs

    if isinstance(intrinsics, rs.intrinsics):
        result = intrinsics
    elif isinstance(intrinsics, dict):
        result = rs.intrinsics()
        for key in ('width', 'height', 'fx', 'fy', 'ppx', 'ppy'):
            setattr(result, key, intrinsics[key])
        result.coeffs = list(intrinsics.get('coeffs', [0.0] * 5))
        name = str(intrinsics.get('model', 'none')).removeprefix('distortion.')
        if name not in ('none', 'modified_brown_conrady', 'inverse_brown_conrady',
                        'ftheta', 'brown_conrady', 'kannala_brandt4'):
            raise ValueError(f'Unsupported RealSense distortion model: {name}')
        result.model = getattr(rs.distortion, name)
    else:
        raise TypeError('intrinsics must be the saved dictionary or rs.intrinsics')
    numbers = [result.fx, result.fy, result.ppx, result.ppy, *result.coeffs]
    if not np.isfinite(numbers).all() or min(result.fx, result.fy) <= 0:
        raise ValueError('Camera intrinsics must be finite, with positive focal lengths.')
    return result


def _points(values, dimension, name):
    result = np.asarray(values, dtype=np.float64)
    if result.ndim < 1 or result.shape[-1] != dimension or result.size == 0:
        raise ValueError(f'{name} must have shape (..., {dimension}) and contain points.')
    if not np.isfinite(result).all():
        raise ValueError(f'{name} must be finite.')
    return result


def _pose(R, t):
    R = np.asarray(R, dtype=np.float64)
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    if R.shape != (3, 3) or t.shape != (3,) or not np.isfinite(R).all() or not np.isfinite(t).all():
        raise ValueError('R must be a finite 3x3 rotation and t a finite length-3 translation.')
    if not np.allclose(R.T @ R, np.eye(3), atol=1e-6) or not np.isclose(np.linalg.det(R), 1, atol=1e-6):
        raise ValueError('R must be a proper orthonormal rotation.')
    center = -R.T @ t
    if center[2] <= 0:
        raise ValueError('The camera must be above the paper (+Z).')
    return R, t, center


def pixel_rays(pixels, intrinsics):
    """Return camera rays with Z=1; input shape (...,2), output (...,3)."""
    import pyrealsense2 as rs

    pixels = _points(pixels, 2, 'pixels')
    intr = _sdk_intrinsics(intrinsics)
    rays = np.array([rs.rs2_deproject_pixel_to_point(intr, p.tolist(), 1.0)
                     for p in pixels.reshape(-1, 2)], dtype=np.float64)
    if not np.isfinite(rays).all():
        raise ValueError('RealSense returned a non-finite camera ray.')
    return rays.reshape(pixels.shape[:-1] + (3,))


def paper_to_pixel(xyz_cm, intrinsics, R, t):
    """Project paper-frame XYZ centimetres to original, distorted RGB pixels."""
    import pyrealsense2 as rs

    xyz = _points(xyz_cm, 3, 'xyz_cm')
    intr = _sdk_intrinsics(intrinsics)
    R, t, _ = _pose(R, t)
    camera = xyz.reshape(-1, 3) @ R.T + t
    if np.any(camera[:, 2] <= 0):
        raise ValueError('Cannot project points on or behind the camera plane.')
    pixels = np.array([rs.rs2_project_point_to_pixel(intr, p.tolist())
                       for p in camera], dtype=np.float64)
    if not np.isfinite(pixels).all():
        raise ValueError('RealSense returned a non-finite pixel.')
    return pixels.reshape(xyz.shape[:-1] + (2,))


def pixel_to_paper(pixels, intrinsics, R, t, height_cm=0.0):
    """Intersect pixel rays with a horizontal plane; return paper-frame XY cm.

    A top-face center on a 2 cm cube uses height_cm=2. Its resulting XY is the
    footprint center estimate, provided that the cube's top is parallel to the
    paper. This is a model-based estimate, not an independently measured point.
    """
    pixels = _points(pixels, 2, 'pixels')
    if not np.isscalar(height_cm) or not np.isfinite(height_cm):
        raise ValueError('height_cm must be a finite scalar.')
    R, _, center = _pose(R, t)
    rays = pixel_rays(pixels, intrinsics).reshape(-1, 3) @ R
    if np.any(np.abs(rays[:, 2]) < 1e-10):
        raise ValueError('A camera ray is parallel to the requested paper plane.')
    distance = (float(height_cm) - center[2]) / rays[:, 2]
    if np.any(distance <= 0):
        raise ValueError('The requested paper-plane intersection is behind the camera.')
    points = center + distance[:, None] * rays
    return points[:, :2].reshape(pixels.shape)


def fit_table_pose(paper_xy_cm, pixels, intrinsics):
    """Fit paper-to-camera R,t from grid intersections; return R,t,diagnostics.

    The camera pose is fitted in normalized camera-ray coordinates. Diagnostics
    contain in-sample reprojection residuals in the original RGB image; these
    residuals do not measure the accuracy of subsequently inferred block centers.
    """
    xy = _points(paper_xy_cm, 2, 'paper_xy_cm')
    pixels = _points(pixels, 2, 'pixels')
    if xy.ndim != 2 or pixels.ndim != 2 or xy.shape != pixels.shape or len(xy) < 4:
        raise ValueError('Need at least four matching Nx2 grid coordinates and pixels.')
    if len(np.unique(xy, axis=0)) != len(xy) or len(np.unique(pixels, axis=0)) != len(pixels):
        raise ValueError('Grid correspondences must be distinct.')
    if np.linalg.matrix_rank(xy - xy.mean(axis=0)) < 2:
        raise ValueError('Paper grid controls must not be collinear.')
    xyz = np.column_stack((xy, np.zeros(len(xy))))
    normalized = np.ascontiguousarray(pixel_rays(pixels, intrinsics)[:, :2])
    ok, rvec, tvec = cv2.solvePnP(xyz, normalized, np.eye(3), None,
                                 flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        raise ValueError('Paper-plane camera pose could not be fitted.')
    R = cv2.Rodrigues(rvec)[0]
    t = tvec.reshape(3)
    R, t, center = _pose(R, t)
    projected = paper_to_pixel(xyz, intrinsics, R, t)
    residual = np.linalg.norm(projected - pixels, axis=1)
    diagnostics = dict(control_count=len(xy), camera_center_cm=center.tolist(),
                       camera_height_cm=float(center[2]),
                       reprojection_rms_px=float(np.sqrt(np.mean(residual ** 2))),
                       reprojection_max_px=float(residual.max()),
                       reprojection_errors_px=residual.tolist())
    return R, t, diagnostics
