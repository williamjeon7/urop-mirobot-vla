"""Export real wrist recordings for Cosmos LIBERO with third-person images disabled.

The upstream reader requires both image keys even in wrist-only mode. Its unused
agentview key is a hard link to the real wrist RGB, not a simulated external view.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import h5py
import numpy as np

from common.proprio import settings_from_gcode
from .action_labels import follow_actions
from .color_calibration import load_profile
from .export_hdf5 import wrist_image
from .prepare import input_hashes, input_hashes_match, read_jsonl

SCHEMA = 'mirobot-cosmos-wrist/1'


def episode_id(episode):
    name = Path(episode).name
    if name.startswith('영상') and name[2:].isascii() and name[2:].isdigit():
        return 'video'+name[2:]
    if not name.isascii() or not all(c.isalnum() or c in '_-' for c in name):
        raise ValueError('Episode name must be 영상N or ASCII letters/digits/_/-.')
    return name


def export_episode(episode, out, target, real_success=False, rotate=0,
                   skip_existing=False, action_generator=follow_actions):
    episode, out = Path(episode), Path(out)
    if target not in ('red', 'green', 'blue') or rotate not in (0, 90, 180, 270):
        raise ValueError('Invalid reviewed target or image rotation.')
    if not real_success:
        raise ValueError('Review the real pickup success before exporting a demonstration.')
    meta = json.loads((episode/'metadata.json').read_text(encoding='utf-8'))
    if not meta.get('complete') or not meta.get('robot'):
        raise ValueError('Need a complete real camera and robot capture.')
    report = json.loads((episode/'alignment_report.json').read_text(encoding='utf-8'))
    if not input_hashes_match(episode, report.get('input_sha256')):
        raise ValueError('Capture inputs changed after alignment. Run prepare again.')
    source_hashes = input_hashes(episode)
    aligned_hash = hashlib.sha256((episode/'aligned.npz').read_bytes()).hexdigest()
    instruction = f'pick up the {target} block on the table'
    output = out/f'MIROBOT_{episode_id(episode)}_SCENE1_{instruction.replace(" ", "_")}_demo.hdf5'
    if output.exists():
        if not skip_existing:
            raise FileExistsError(output)
        with h5py.File(output, 'r') as f:
            attrs = f['data/demo_0'].attrs
            if (attrs.get('schema') != SCHEMA or
                    attrs.get('instruction') != instruction or attrs.get('wrist_rotate_ccw') != rotate or
                    attrs.get('observation_mode') != 'wrist_only' or
                    attrs.get('aligned_sha256') != aligned_hash or
                    json.loads(attrs.get('input_sha256', '{}')) != source_hashes or
                    f['data/demo_0/obs/agentview_rgb'].id != f['data/demo_0/obs/eye_in_hand_rgb'].id):
                raise ValueError(f'Existing output differs from current inputs/options: {output}')
            for name, digest in json.loads(attrs.get('source_png_sha256', '{}')).items():
                if hashlib.sha256((episode/name).read_bytes()).hexdigest() != digest:
                    raise ValueError(f'Existing output source PNG changed: {episode/name}')
            demo = f['data/demo_0']
            n = len(demo['actions'])
            if (demo['actions'].shape != (n,7) or demo['robot_states'].shape != (n,9) or
                    demo['obs/eye_in_hand_rgb'].shape != (n,256,256,3) or
                    not np.isfinite(demo['actions'][:]).all() or
                    not np.allclose(np.diff(demo['timestamps'][:]), .05, atol=1e-7)):
                raise ValueError(f'Existing output has invalid arrays: {output}')
            return dict(path=str(output), status='existing', steps=len(f['data/demo_0/actions']),
                        instruction=instruction, **json.loads(attrs.get('label_report', '{}')))
    with np.load(episode/'aligned.npz', allow_pickle=False) as saved:
        aligned = {k: saved[k] for k in saved.files}
    n = len(aligned['gripper_actions'])
    if (n < 16 or aligned['robot_states'].shape != (n+1, 9) or
            aligned['times'].shape != (n+1,) or aligned['frame_indices'].shape != (n,) or
            aligned['frame_error_s'].shape != (n,) or
            not np.allclose(np.diff(aligned['times']), .05, atol=1e-7) or
            not all(np.isfinite(v).all() for v in aligned.values())):
        raise ValueError('Invalid aligned timeline or state arrays.')
    frames = read_jsonl(episode/'frames.jsonl')
    indices = aligned['frame_indices']
    if not np.issubdtype(indices.dtype, np.integer) or np.min(indices) < 0 or np.max(indices) >= len(frames):
        raise ValueError('Frame index outside the recorded PNG timeline.')
    profile = load_profile(episode/'color_profile.json')
    reference = read_jsonl(episode/'reference.jsonl')[0]['meta']
    settings = settings_from_gcode((episode/'source.gcode').read_text(encoding='utf-8'))
    actions, gaps, label_report = action_generator(aligned, reference, settings['scale'])
    if (actions.shape != (n, 7) or gaps.shape != (n, 2) or
            not np.isfinite(actions).all() or np.max(np.abs(actions)) > 1.000001):
        raise ValueError('Invalid generated action labels.')
    out.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix('.hdf5.partial')
    created_partial = False
    try:
        with h5py.File(partial, 'x') as f:
            created_partial = True
            data = f.create_group('data')
            data.attrs['instruction'] = instruction
            demo = data.create_group('demo_0')
            obs = demo.create_group('obs')
            wrist = obs.create_dataset('eye_in_hand_rgb', shape=(n,256,256,3), dtype=np.uint8,
                                       chunks=(1,256,256,3), compression='lzf')
            cache = {}
            png_hashes = {}
            for k, index in enumerate(indices):
                index = int(index)
                if index not in cache:
                    source = episode/frames[index]['file']
                    cache = {index: wrist_image(source, rotate, profile)}
                    png_hashes[frames[index]['file']] = hashlib.sha256(source.read_bytes()).hexdigest()
                wrist[k] = cache[index]
            obs['agentview_rgb'] = wrist
            for key, value in [('actions', actions.astype(np.float32)),
                    ('robot_states', aligned['robot_states'][:-1].astype(np.float32)),
                    ('timestamps', aligned['times'][:-1]), ('frame_indices', indices),
                    ('frame_error_s', aligned['frame_error_s']), ('follow_error_mm_deg', gaps)]:
                demo.create_dataset(key, data=value)
            attrs = dict(schema=SCHEMA, instruction=instruction, observation_mode='wrist_only',
                agentview_is_wrist_alias=True, source_episode=episode.name,
                recorded_capture_color=meta['color'], reviewed_target=target, real_success=True,
                review_source='user confirmed real pickup and target colour',
                input_sha256=json.dumps(source_hashes, sort_keys=True), aligned_sha256=aligned_hash,
                source_png_sha256=json.dumps(png_hashes, sort_keys=True), dt=.05,
                wrist_rotate_ccw=rotate, color_profile_applied=True,
                accepted_max_frame_ms=report.get('accepted_max_frame_ms', 40),
                default_frame_limit_passed=bool((np.abs(aligned['frame_error_s']) <= .04).all()),
                action_method=label_report['method'], label_report=json.dumps(label_report),
                image_orientation='upright RGB, center square crop, no overlays')
            for key, value in attrs.items():
                demo.attrs[key] = value
            demo.create_dataset('alignment_report_json', data=json.dumps(report))
        if (input_hashes(episode) != source_hashes or
                hashlib.sha256((episode/'aligned.npz').read_bytes()).hexdigest() != aligned_hash):
            raise ValueError('Inputs changed while exporting; output was not published.')
        # Same-directory hard link is an atomic, exclusive publication (no overwrite).
        os.link(partial, output)
        partial.unlink()
    except BaseException:
        if created_partial and partial.exists():
            partial.unlink()
        raise
    return dict(path=str(output), status='created', steps=n, instruction=instruction, **label_report)


def main():
    import cv2
    cv2.setNumThreads(2)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episodes', type=Path, nargs='+')
    parser.add_argument('--out', type=Path, required=True, help='Output suite, e.g. docs/W9/data/hdf5/mirobot_real')
    parser.add_argument('--target', choices=('red','green','blue'), required=True, help='Reviewed target, independent of old capture metadata')
    parser.add_argument('--real-success', action='store_true')
    parser.add_argument('--rotate', type=int, choices=(0,90,180,270), default=0)
    parser.add_argument('--skip-existing', action='store_true')
    args = parser.parse_args()
    results = []
    failed = False
    for episode in args.episodes:
        try:
            result = export_episode(episode, args.out, args.target, args.real_success,
                                    args.rotate, args.skip_existing)
        except Exception as error:
            failed = True
            result = dict(episode=str(episode), status='failed', error=f'{type(error).__name__}: {error}')
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out.parent/'real_export_summary.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
