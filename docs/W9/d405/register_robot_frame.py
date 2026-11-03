"""Compose measured paper/camera data with user ruler measurements at one pose.

No robot or camera I/O. The result assumes paper/Mirobot axes are parallel and
the supplied tool vector reaches the same open-finger-tip midpoint whose height
the user measured. This is not an independently verified hand-eye calibration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

from common.proprio import settings_from_gcode
from common.rotation import euler_xyz_deg_to_quat
from common.workspace import mirobot_flange_to_grip_mm


def _vector(value, length, name):
    try:
        values = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{name} must contain {length} finite numbers.') from error
    if values.shape != (length,) or not np.isfinite(values).all():
        raise ValueError(f'{name} must contain {length} finite numbers.')
    return values


def _rigid(matrix, name):
    try:
        matrix = np.asarray(matrix, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{name} must be a finite 4x4 rigid transform.') from error
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError(f'{name} must be a finite 4x4 rigid transform.')
    rotation = matrix[:3, :3]
    if (not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-8)
            or not np.allclose(rotation.T@rotation, np.eye(3), atol=1e-6)
            or not np.isclose(np.linalg.det(rotation), 1., atol=1e-6)):
        raise ValueError(f'{name} must have a proper orthonormal rotation and homogeneous last row.')
    return matrix


def build_registration(table_camera_report, j1_paper_xy_mm, tip_height_mm,
                       initial_flange_cart, tool_mm, *, axes_parallel_confirmed=False):
    """Return SI transforms without inventing any missing user measurement.

    Paper T and Mirobot M are assumed to share +X,+Y,+Z directions. J1's paper
    coordinates supply XY translation; a ruler height of the specified tool point
    above the paper supplies Z translation. Camera C is native depth optical.
    """
    if axes_parallel_confirmed is not True:
        raise ValueError('Explicit confirmation of parallel paper/Mirobot axes is required.')
    if (not isinstance(table_camera_report, dict)
            or table_camera_report.get('format') != 'w9-depth-paper-registration/1'
            or table_camera_report.get('unit') != 'm'):
        raise ValueError('Need a metric w9-depth-paper-registration/1 report.')
    c_from_t = _rigid(table_camera_report.get('T_C_depth_from_T'), 'T_C_depth_from_T')
    j1 = _vector(j1_paper_xy_mm, 2, 'J1 paper XY (mm)')
    flange = _vector(initial_flange_cart, 6, 'Initial flange XYZ mm / ABC degrees')
    tool = _vector(tool_mm, 3, 'Flange-local tool vector (mm)')
    if isinstance(tip_height_mm, bool) or not isinstance(tip_height_mm, (int, float)) or not math.isfinite(tip_height_mm) or tip_height_mm <= 0:
        raise ValueError('Measured tool-tip height above paper must be a positive finite number in mm.')
    orientation = euler_xyz_deg_to_quat(*flange[3:])
    tip = np.asarray(mirobot_flange_to_grip_mm(flange[:3], orientation, tuple(tool)))
    m_from_t = np.eye(4)
    m_from_t[:2, 3] = -j1/1000
    m_from_t[2, 3] = (tip[2]-tip_height_mm)/1000
    m_from_c = m_from_t@np.linalg.inv(c_from_t)
    return {
        'format': 'w9-robot-paper-registration/1', 'unit': 'm',
        'registration_type': 'user_ruler+nativeDepth',
        'direction': 'p_M_m = T_M_from_T * p_T_m; p_M_m = T_M_from_C_depth * p_C_depth_m',
        'T_M_from_T': m_from_t.tolist(), 'T_T_from_M': np.linalg.inv(m_from_t).tolist(),
        'T_C_depth_from_T': c_from_t.tolist(), 'T_T_from_C_depth': np.linalg.inv(c_from_t).tolist(),
        'T_M_from_C_depth': m_from_c.tolist(), 'T_C_depth_from_M': np.linalg.inv(m_from_c).tolist(),
        'user_measurements': {
            'j1_centre_paper_xy_mm': j1.tolist(), 'open_finger_tip_midpoint_height_above_paper_mm': float(tip_height_mm),
        },
        'initial_flange_cart': flange.tolist(), 'valid_initial_pose_cart': flange.tolist(),
        'flange_cart_units': ['mm', 'mm', 'mm', 'degree', 'degree', 'degree'],
        'flange_ABC_convention': 'extrinsic XYZ; R=Rz(C) Ry(B) Rx(A)',
        'flange_local_tool_mm': tool.tolist(), 'initial_tool_point_mirobot_mm': tip.tolist(),
        'paper_origin_mirobot_mm': (m_from_t[:3, 3]*1000).tolist(),
        'axes_parallel_confirmed': True,
        'assumptions': [
            'Paper and Mirobot +X,+Y,+Z are parallel; paper is level relative to robot base.',
            'Controller base XY origin lies on the J1 rotation axis.',
            'The supplied flange-local tool vector reaches the measured open-finger-tip midpoint.',
            'Robot status and depth snapshot describe the same unchanged arm/camera pose.',
            'Paper, robot base and camera bracket did not move between measurements.',
        ],
        'independently_validated': False,
        'camera_mount': 'forearm',
        'camera_transform_validity': 'Initial measured arm pose only. Arm motion invalidates the fixed camera transform; constant Cartesian ABC is not sufficient to preserve camera pose.',
        'limitation': 'Ruler/tool/parallel-axis assumptions are not independently validated; this is not moving-camera hand-eye calibration.',
        'table_camera_diagnostics': {key: table_camera_report[key] for key in (
            'snapshot', 'coordinate_source', 'depth_plane_rms_mm', 'heldout_grid_rms_mm', 'heldout_grid_max_mm')
            if key in table_camera_report},
    }


def build_registration_from_tip(table_camera_report, tip_paper_xy_mm, tip_height_mm,
                                initial_flange_cart, tool_mm, *, axes_parallel_confirmed=False):
    """Use a measured tool-tip vertical projection as the paper XY anchor.

    This path does not measure or assume the physical J1 centre. It derives the
    controller Cartesian XY origin's paper coordinates from the measured tip
    projection and the reported flange pose plus the existing tool vector.
    """
    tip_paper = _vector(tip_paper_xy_mm, 2, 'Measured tool-tip projection paper XY (mm)')
    flange = _vector(initial_flange_cart, 6, 'Initial flange XYZ mm / ABC degrees')
    tool = _vector(tool_mm, 3, 'Flange-local tool vector (mm)')
    tip_m = np.asarray(mirobot_flange_to_grip_mm(
        flange[:3], euler_xyz_deg_to_quat(*flange[3:]), tuple(tool)))
    cartesian_origin_paper = tip_paper-tip_m[:2]
    result = build_registration(table_camera_report, cartesian_origin_paper, tip_height_mm,
                                flange, tool, axes_parallel_confirmed=axes_parallel_confirmed)
    # The shared transform math uses an origin XY pair. Do not mislabel this
    # derived Cartesian origin as a user measurement of the hidden J1 centre.
    result['xy_anchor'] = 'user_measured_open_finger_tip_midpoint_vertical_projection'
    result['user_measurements'].pop('j1_centre_paper_xy_mm')
    result['user_measurements']['open_finger_tip_midpoint_paper_xy_mm'] = tip_paper.tolist()
    result['derived_controller_cartesian_xy_origin_paper_mm'] = cartesian_origin_paper.tolist()
    result['assumptions'] = [item for item in result['assumptions']
                             if item != 'Controller base XY origin lies on the J1 rotation axis.']
    return result


def _point_transform(point, transform, scale):
    point = _vector(point, 3, 'Point XYZ')*scale
    return (transform[:3, :3]@point+transform[:3, 3])*1000


def paper_to_mirobot(xyz_cm, report):
    """Paper XYZ centimetres -> Mirobot XYZ millimetres using a saved registration."""
    if report.get('format') != 'w9-robot-paper-registration/1' or report.get('unit') != 'm':
        raise ValueError('Need a metric robot/paper registration report.')
    return _point_transform(xyz_cm, _rigid(report.get('T_M_from_T'), 'T_M_from_T'), .01).tolist()


def depth_to_mirobot(xyz_m, report):
    """Native depth-camera XYZ metres -> Mirobot XYZ mm at the recorded pose only."""
    if report.get('format') != 'w9-robot-paper-registration/1' or report.get('unit') != 'm':
        raise ValueError('Need a metric robot/paper registration report.')
    return _point_transform(xyz_m, _rigid(report.get('T_M_from_C_depth'), 'T_M_from_C_depth'), 1.).tolist()


def initial_pose_from_status(document):
    """Read an unchanged, Idle pose from at least three saved status responses."""
    rows = document.get('rows') if isinstance(document, dict) else None
    if not isinstance(rows, list) or len(rows) < 3:
        raise ValueError('Need at least three saved Idle robot status rows.')
    poses = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid robot status row.')
        state = row.get('state')
        if not state:
            raw = row.get('raw', '')
            if not isinstance(raw, str) or not raw.lstrip().startswith('<'):
                raise ValueError('Each robot status must identify Idle state.')
            state = re.split(r'[,|]', raw.strip().strip('<>'), maxsplit=1)[0]
        if not isinstance(state, str) or state.lower() != 'idle':
            raise ValueError('Robot status is not Idle; capture stationary status again.')
        poses.append(_vector(row.get('cart'), 6, 'Robot Cartesian pose'))
    values = np.asarray(poses)
    offsets = (values[:, 3:]-values[0, 3:]+180) % 360-180
    if np.max(np.ptp(values[:, :3], axis=0)) > .5 or np.max(np.ptp(offsets, axis=0)) > .5:
        raise ValueError('Saved robot status is not stable within 0.5mm/0.5degree.')
    result = np.median(values, axis=0)
    result[3:] = values[0, 3:]+np.median(offsets, axis=0)
    return result.tolist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--table-report', type=Path, required=True)
    parser.add_argument('--robot-status', type=Path, required=True)
    xy_anchor = parser.add_mutually_exclusive_group(required=True)
    xy_anchor.add_argument('--j1-paper-mm', nargs=2, type=float, metavar=('X', 'Y'),
                            help='Measured J1 centre paper XY, if the physical centre is accessible')
    xy_anchor.add_argument('--tip-paper-mm', nargs=2, type=float, metavar=('X', 'Y'),
                            help='Measured vertical projection of current open-finger-tip midpoint on paper')
    parser.add_argument('--tip-height-mm', type=float, required=True)
    parser.add_argument('--tool-gcode', type=Path, required=True)
    parser.add_argument('--axes-parallel-confirmed', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    table = json.loads(args.table_report.read_text(encoding='utf-8'))
    status = json.loads(args.robot_status.read_text(encoding='utf-8'))
    tool = settings_from_gcode(args.tool_gcode.read_text(encoding='utf-8'))['tool_mm']
    pose = initial_pose_from_status(status)
    if args.tip_paper_mm is not None:
        result = build_registration_from_tip(table, args.tip_paper_mm, args.tip_height_mm, pose, tool,
                                             axes_parallel_confirmed=args.axes_parallel_confirmed)
    else:
        result = build_registration(table, args.j1_paper_mm, args.tip_height_mm, pose, tool,
                                    axes_parallel_confirmed=args.axes_parallel_confirmed)
    result['source_files'] = {
        name: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        for name, path in [('table_report', args.table_report), ('robot_status', args.robot_status), ('tool_gcode', args.tool_gcode)]
    }
    with args.out.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print('Saved:', args.out)
    print('Paper origin in Mirobot mm:', result['paper_origin_mirobot_mm'])
    print('Camera transform is valid only at the recorded initial forearm pose; independent validation remains pending.')


if __name__ == '__main__':
    main()
