"""Resample a captured episode at 20 Hz. No simulator, robot motion or model download."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np

from common.proprio import fingers, mirobot_to_libero_pose, robot_states, settings_from_gcode
from common.rotation import quat_xyzw_to_wxyz
from common.workspace import grip_to_flange

DT = 0.05


def _input_texts(episode):
    """Known text inputs, with Git's LF/CRLF checkout differences removed."""
    names = ['metadata.json', 'source.gcode', 'reference.jsonl', 'frames.jsonl', 'robot.jsonl']
    if (Path(episode)/'color_profile.json').exists():
        names.append('color_profile.json')
    return {name: (Path(episode)/name).read_bytes().replace(b'\r\n', b'\n') for name in names}


def input_hashes(episode):
    """Hash canonical LF text so reports survive Windows/Linux Git checkouts."""
    return {name: hashlib.sha256(content).hexdigest()
            for name, content in _input_texts(episode).items()}


def input_hashes_match(episode, recorded):
    """Accept canonical hashes and legacy raw CRLF hashes, without hiding edits."""
    texts = _input_texts(episode)
    if not isinstance(recorded, dict) or recorded.keys() != texts.keys():
        return False
    return all(recorded[name] in (
        hashlib.sha256(content).hexdigest(),
        hashlib.sha256(content.replace(b'\n', b'\r\n')).hexdigest(),
    ) for name, content in texts.items())


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def ordered_times(rows, name):
    t = np.array([r['t_s'] for r in rows], dtype=np.float64)
    if len(t) < 2 or not np.all(np.isfinite(t)) or np.any(np.diff(t) <= 0):
        raise ValueError(f'{name}: need at least two strictly increasing finite timestamps.')
    return t


def slerp(q0, q1, alpha):
    q0, q1 = np.asarray(q0, float), np.asarray(q1, float)
    q0, q1 = q0 / np.linalg.norm(q0), q1 / np.linalg.norm(q1)
    dot = float(np.dot(q0, q1))
    if dot < 0:
        q1, dot = -q1, -dot
    if dot > 0.9995:
        q = (1-alpha)*q0 + alpha*q1
        return q / np.linalg.norm(q)
    theta = math.acos(np.clip(dot, -1, 1))
    return (math.sin((1-alpha)*theta)*q0 + math.sin(alpha*theta)*q1)/math.sin(theta)


def nearest_indices(source, target, max_error):
    right = np.searchsorted(source, target).clip(0, len(source)-1)
    left = (right-1).clip(0, len(source)-1)
    idx = np.where(abs(source[left]-target) <= abs(source[right]-target), left, right)
    error = source[idx] - target
    if np.max(abs(error)) > max_error:
        raise ValueError(f'Camera frame too far from grid: {np.max(abs(error))*1000:.1f} ms.')
    return idx, error


def gripper_track(events, target_times, duration, initial_s, open_s, closed_s):
    def closure(s):
        c = (s-open_s)/(closed_s-open_s)
        if not -0.001 <= c <= 1.001:
            raise ValueError(f'Gripper S{s} is outside calibrated open/closed endpoints.')
        return float(np.clip(c, 0, 1))
    commands = []
    start, current, goal = -float('inf'), closure(initial_s), closure(initial_s)
    for event in events:
        match = re.fullmatch(r'M4\s+S(\d+(?:\.\d+)?)', event.get('cmd', ''), re.I)
        if match:
            t = event['t_s']
            new_goal = closure(float(match.group(1)))
            if new_goal == goal:
                continue  # holding the same key must not restart the servo transition
            current = current + (goal-current)*min(1, max(0, (t-start)/duration))
            start, goal = t, new_goal
            commands.append((start, current, goal))
    actual, control = [], []
    for t in target_times:
        value, setpoint = closure(initial_s), closure(initial_s)
        for start, current, goal in commands:
            if start > t:
                break
            value = current + (goal-current)*min(1, (t-start)/duration)
            setpoint = goal
        actual.append(value)
        control.append(1.0 if setpoint >= 0.5 else -1.0)
    return np.array(actual), np.array(control)


def prepare(episode, max_frame_ms=40, max_state_gap_ms=150, camera_latency_ms=0,
            start=None, end=None):
    episode = Path(episode)
    meta = json.loads((episode/'metadata.json').read_text(encoding='utf-8'))
    if not meta.get('complete') or not meta.get('robot'):
        raise ValueError('Need a complete camera + robot capture, not a camera-only test.')
    reference = read_jsonl(episode/'reference.jsonl')[0]['meta']
    if reference['seed'] != meta['seed'] or reference['task'] != meta['color']:
        raise ValueError('Reference scene does not match capture.')
    frames = read_jsonl(episode/'frames.jsonl')
    events = read_jsonl(episode/'robot.jsonl')
    states = [r for r in events if r['kind'] == 'state']
    if not any(r['kind'] == 'complete' for r in events):
        raise ValueError('Robot did not complete all commands.')
    ft = ordered_times(frames, 'frames') - camera_latency_ms/1000
    rt = ordered_times(states, 'robot')
    lo, hi = max(ft[0], rt[0]), min(ft[-1], rt[-1])
    if meta.get('teleop'):
        starts = [r['t_s'] for r in events if r['kind'] == 'capture_start']
        ends = [r['t_s'] for r in events if r['kind'] == 'capture_end']
        if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
            raise ValueError('Need exactly one valid F8/F9 capture interval.')
        lo, hi = max(lo, starts[0]), min(hi, ends[0])
    if start is not None:
        lo = max(lo, start)
    if end is not None:
        hi = min(hi, end)
    count = math.floor((hi-lo)/DT + 1e-8)
    if count < 16:
        raise ValueError('Need at least 16 actions (0.8 seconds) of overlapping data.')
    times = lo + np.arange(count+1)*DT  # last pose is only the next-action target
    relevant = (rt[1:] >= times[0]) & (rt[:-1] <= times[-1])
    gap = float(np.diff(rt)[relevant].max())
    if gap > max_state_gap_ms/1000:
        raise ValueError(f'Robot state gap {gap*1000:.1f} ms exceeds limit; do not invent missing motion.')
    indices, errors = nearest_indices(ft, times[:-1], max_frame_ms/1000)
    settings = settings_from_gcode((episode/'source.gcode').read_text(encoding='utf-8'))
    ref_q = quat_xyzw_to_wxyz(reference['start_eef_quat_xyzw'])
    ref_flange = grip_to_flange(reference['start_eef_pos'], ref_q)
    poses = [mirobot_to_libero_pose(r['cart'][:3], r['cart'][3:], ref_flange, ref_q, settings) for r in states]
    pos = np.array([v[0] for v in poses])
    quats = np.array([v[1] for v in poses])
    if not np.all(np.isfinite(pos)) or not np.all(np.isfinite(quats)):
        raise ValueError('Non-finite converted robot poses.')
    right = np.searchsorted(rt, times, side='right').clip(1, len(rt)-1)
    left = right-1
    alpha = (times-rt[left])/(rt[right]-rt[left])
    if np.any(alpha < -1e-7) or np.any(alpha > 1+1e-7):
        raise ValueError('Interpolation would extrapolate beyond robot coverage.')
    pp = pos[left]*(1-alpha[:, None]) + pos[right]*alpha[:, None]
    qq = np.array([slerp(quats[l], quats[r], u) for l, r, u in zip(left, right, alpha)])
    closed, control = gripper_track(events, times, meta['gripper_seconds'], meta['initial_s'],
                                     meta['open_s'], meta['closed_s'])
    proprio = np.array([robot_states(fingers(c), v, tuple(q)) for c, v, q in zip(closed, pp, qq)], np.float32)
    result = dict(times=times, positions=pp, quaternions_wxyz=qq, robot_states=proprio,
                  frame_indices=indices, frame_error_s=errors, gripper_actions=control[1:])
    report = dict(steps=count, dt=DT, robot_hz_median=1/float(np.median(np.diff(rt))),
                  max_robot_gap_ms=gap*1000, max_frame_error_ms=float(abs(errors).max()*1000),
                  repeated_frames=int(len(indices)-len(np.unique(indices))),
                  camera_latency_ms=camera_latency_ms,
                  skipped_camera_frame_numbers=int(sum(max(0, b['number']-a['number']-1)
                                                       for a, b in zip(frames, frames[1:]))),
                  timing_note='Host receipt alignment; camera exposure and serial latency remain uncertain.',
                  interpolation='linear position; quaternion SLERP; commanded gripper linear travel')
    report['input_sha256'] = input_hashes(episode)
    return result, report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('episode', type=Path)
    p.add_argument('--max-frame-ms', type=float, default=40)
    p.add_argument('--max-state-gap-ms', type=float, default=150)
    p.add_argument('--camera-latency-ms', type=float, default=0, help='Measured camera receipt delay to subtract')
    p.add_argument('--start', type=float, help='Trim in capture-clock seconds')
    p.add_argument('--end', type=float)
    a = p.parse_args()
    if a.max_frame_ms <= 0 or a.max_state_gap_ms <= 0 or a.camera_latency_ms < 0:
        p.error('Positive error limits and nonnegative latency required.')
    result, report = prepare(a.episode, a.max_frame_ms, a.max_state_gap_ms, a.camera_latency_ms, a.start, a.end)
    np.savez_compressed(a.episode/'aligned.npz', **result)
    (a.episode/'alignment_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    print('Saved aligned.npz. This is not yet a training HDF5 dataset.')


if __name__ == '__main__':
    main()
