"""Offline Panda following -> agentview + OSC_POSE + D405 wrist -> LIBERO HDF5.

Run in the server LIBERO/Cosmos environment. Does not contact the real robot.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import cv2
import h5py
import numpy as np

from common.rotation import quat_xyzw_to_wxyz
from common.servo import pose_gap, servo_action
from .prepare import input_hashes_match, read_jsonl
from .capture_storage import read_image

REPO = Path(__file__).resolve().parents[3]


def wrist_image(path, rotate=0, color_profile=None):
    image = read_image(path)
    if image is None:
        raise ValueError(f'Unreadable RGB PNG: {path}')
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    from .color_calibration import apply_rgb
    image = apply_rgb(image, color_profile)
    image = np.rot90(image, rotate//90)
    h, w = image.shape[:2]
    n = min(h, w)
    image = image[(h-n)//2:(h+n)//2, (w-n)//2:(w+n)//2]
    return cv2.resize(image, (256, 256), interpolation=cv2.INTER_AREA)


def write_demo(path, instruction, primary, wrist, actions, states, times, attrs, frame_error, gap):
    # Exclusive creation, never append to a possibly partially written training file.
    with h5py.File(path, 'x') as f:
        data = f.create_group('data')
        data.attrs['instruction'] = instruction
        demo = data.create_group('demo_0')
        obs = demo.create_group('obs')
        for name, value in [('agentview_rgb', primary), ('eye_in_hand_rgb', wrist)]:
            obs.create_dataset(name, data=np.asarray(value, np.uint8), compression='lzf')
        demo.create_dataset('actions', data=np.asarray(actions, np.float32))
        demo.create_dataset('robot_states', data=np.asarray(states, np.float32))
        demo.create_dataset('timestamps', data=times)
        demo.create_dataset('frame_error_s', data=frame_error)
        demo.create_dataset('follow_error_mm_deg', data=gap)
        for key, value in attrs.items():
            demo.attrs[key] = value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('episode', type=Path)
    p.add_argument('--out', type=Path, required=True, help='suite directory, e.g. docs/W9/data/hdf5/mirobot_real')
    p.add_argument('--real-success', action='store_true', help='You reviewed the real pickup and it succeeded')
    p.add_argument('--layout-confirmed', action='store_true', help='Real blocks match this seed and calibrated mapping')
    p.add_argument('--rotate', type=int, choices=[0, 90, 180, 270], default=0, help='CCW wrist rotation')
    p.add_argument('--max-follow-mm', type=float, default=5, help='Provisional real-robot-equivalent position limit')
    p.add_argument('--max-follow-deg', type=float, default=2)
    a = p.parse_args()
    if not a.real_success or not a.layout_confirmed:
        p.error('Review the real pickup and block layout; both review flags are required.')
    if a.max_follow_mm <= 0 or a.max_follow_deg <= 0:
        p.error('Follow error limits must be positive.')
    meta = json.loads((a.episode/'metadata.json').read_text(encoding='utf-8'))
    if not meta.get('complete') or not meta.get('robot'):
        raise ValueError('Incomplete capture.')
    ref = read_jsonl(a.episode/'reference.jsonl')[0]['meta']
    frames = read_jsonl(a.episode/'frames.jsonl')
    from .color_calibration import load_profile
    profile_path = a.episode/'color_profile.json'
    color_profile = load_profile(profile_path) if profile_path.is_file() else None
    with np.load(a.episode/'aligned.npz', allow_pickle=False) as aligned:
        aligned = {k: aligned[k] for k in aligned.files}
    report = json.loads((a.episode/'alignment_report.json').read_text(encoding='utf-8'))
    if not input_hashes_match(a.episode, report.get('input_sha256')):
        raise ValueError('Capture inputs changed after alignment. Run prepare again.')
    instruction = f"pick up the {meta['color']} block on the table"
    # Lazy simulator import: --help and image/HDF5 checks work on a CPU laptop.
    os.environ.setdefault('MUJOCO_GL', 'wgl' if sys.platform == 'win32' else 'egl')
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    sys.path.insert(0, str(REPO/'docs/W6/rgb_blocks'))
    from preview import create_env
    from common.proprio import settings_from_gcode
    settings = settings_from_gcode((a.episode/'source.gcode').read_text(encoding='utf-8'))
    env = create_env(resolution=256, cameras=('agentview',), task=meta['color'],
                     seed=meta['seed'], size_mm=ref['block_size_mm'], ignore_done=True)
    primary, wrists, actions, gaps, success = [], [], [], [], []
    try:
        obs = env.reset()
        ref_q = quat_xyzw_to_wxyz(ref['start_eef_quat_xyzw'])
        dp, dq = pose_gap(obs['robot0_eef_pos'], quat_xyzw_to_wxyz(obs['robot0_eef_quat']),
                          ref['start_eef_pos'], ref_q)
        if dp > 0.001 or dq > 0.1:
            raise ValueError('Simulator reset differs from G-code reference (>1 mm/0.1 deg).')
        for name, xyz in ref['blocks_start_xyz_m'].items():
            body = env.env.obj_body_id[name]
            if np.linalg.norm(env.sim.data.body_xpos[body]-xyz) > 0.001:
                raise ValueError(f'Simulated block layout differs from reference: {name}')
        if env.check_success():
            raise ValueError('Simulated task was already successful before actions.')
        pos, quat = aligned['positions'], aligned['quaternions_wxyz']
        for k, grip in enumerate(aligned['gripper_actions']):
            current_q = quat_xyzw_to_wxyz(obs['robot0_eef_quat'])
            dp, dq = pose_gap(obs['robot0_eef_pos'], current_q, pos[k], tuple(quat[k]))
            gaps.append([dp*1000*settings['scale'], dq])
            # obs[k] BEFORE action[k]; next physical pose is the action target.
            primary.append(np.flipud(obs['agentview_image']).copy())
            wrists.append(wrist_image(a.episode/frames[int(aligned['frame_indices'][k])]['file'], a.rotate, color_profile))
            action = servo_action(obs['robot0_eef_pos'], current_q, pos[k+1], tuple(quat[k+1]), float(grip))
            actions.append(action)
            obs, _, _, _ = env.step(action)
            target = env.env.objects_dict[env.rgb_task['target_object']]
            grasp = env.env._check_grasp(env.env.robots[0].gripper, target)
            success.append(bool(env.check_success() and grasp))
    finally:
        env.close()
    gaps = np.asarray(gaps)
    report.update(max_follow_mm=float(gaps[:, 0].max()), max_follow_deg=float(gaps[:, 1].max()),
                  simulated_success=bool(len(success) >= 10 and all(success[-10:])),
                  accepted_follow_mm=a.max_follow_mm, accepted_follow_deg=a.max_follow_deg)
    (a.episode/'export_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if not report['simulated_success']:
        raise ValueError('Panda did not hold the target up for the last 0.5 s; no training HDF5 written.')
    if report['max_follow_mm'] > a.max_follow_mm or report['max_follow_deg'] > a.max_follow_deg:
        raise ValueError('Follow error exceeds limits; inspect export_report.json. No HDF5 written.')
    a.out.mkdir(parents=True, exist_ok=True)
    ep_id = a.episode.name
    if ep_id.startswith('영상') and ep_id[2:].isascii() and ep_id[2:].isdigit():
        ep_id = 'video' + ep_id[2:]
    if not ep_id.isascii() or not all(c.isalnum() or c in '_-' for c in ep_id):
        raise ValueError('Use an ASCII episode directory name with letters/digits/_/-.')
    path = a.out/f"MIROBOT_{ep_id}_SCENE1_{instruction.replace(' ', '_')}_demo.hdf5"
    temp = path.with_suffix('.hdf5.partial')
    if path.exists() or temp.exists():
        raise FileExistsError(f'Output exists: {path} or {temp}')
    attrs = dict(seed=meta['seed'], source_episode=a.episode.name, real_success=True,
                 simulated_success=True, dt=0.05, wrist_rotate_ccw=a.rotate,
                 image_orientation='upright RGB, no overlay',
                 color_profile_applied=bool(color_profile),
                 max_follow_mm=report['max_follow_mm'], max_follow_deg=report['max_follow_deg'])
    write_demo(temp, instruction, primary, wrists, actions, aligned['robot_states'][:-1],
               aligned['times'][:-1], attrs, aligned['frame_error_s'], gaps)
    temp.rename(path)
    print('Wrote:', path)


if __name__ == '__main__':
    main()
