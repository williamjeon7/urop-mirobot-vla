"""Check LIBERO HDF5 structure on a CPU laptop; optionally verify real T5 embeddings."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import numpy as np


def instruction_from_name(name):
    if not name.endswith('_demo.hdf5'):
        raise ValueError(f'Expected *_demo.hdf5: {name}')
    text = ''
    for word in name[:-10].split('_'):
        text = '' if 'SCENE' in word else text + word + ' '
    return text.strip()


def check(root):
    files = sorted(Path(root).glob('*/*.hdf5'))
    if not files:
        raise ValueError('No HDF5 found. Expected <data-dir>/<suite>/*_demo.hdf5.')
    suites, instructions, episodes = {}, set(), 0
    for path in files:
        command = instruction_from_name(path.name)
        if not command:
            raise ValueError(f'Empty filename instruction: {path}')
        instructions.add(command)
        with h5py.File(path, 'r') as f:
            if f['data'].attrs.get('instruction', command) != command:
                raise ValueError(f'Instruction attribute differs from filename: {path}')
            for name, demo in f['data'].items():
                if not isinstance(demo, h5py.Group):
                    raise ValueError(f'Unexpected item in data: {name}')
                n = len(demo['actions'])
                if n < 16:
                    raise ValueError(f'{path}/{name}: need >=16 steps.')
                for key, shape in [('actions', (n, 7)), ('robot_states', (n, 9)),
                                   ('obs/agentview_rgb', (n, 256, 256, 3)),
                                   ('obs/eye_in_hand_rgb', (n, 256, 256, 3))]:
                    value = demo[key]
                    if value.shape != shape:
                        raise ValueError(f'{path}/{name}/{key}: {value.shape} != {shape}')
                    if key.startswith('obs/'):
                        if value.dtype != np.uint8:
                            raise ValueError(f'{key}: RGB must be uint8.')
                    elif not np.issubdtype(value.dtype, np.floating) or not np.all(np.isfinite(value[:])):
                        raise ValueError(f'{key}: finite floating-point values required.')
                if np.max(abs(demo['actions'][:])) > 1.0001:
                    raise ValueError(f'{path}: OSC_POSE action outside [-1,1].')
                if not np.allclose(np.linalg.norm(demo['robot_states'][:, 5:9], axis=1), 1, atol=1e-3):
                    raise ValueError(f'{path}: non-unit quaternion in robot_states.')
                if 'timestamps' in demo and not np.allclose(np.diff(demo['timestamps'][:]), 0.05, atol=1e-7):
                    raise ValueError('Timesteps are not 0.05 s apart.')
                episodes += 1
                suites[path.parent.name] = suites.get(path.parent.name, 0)+n
    return dict(files=len(files), episodes=episodes, steps=sum(suites.values()),
                steps_by_suite=suites, instructions=sorted(instructions))


def check_embeddings(path, instructions):
    # Only load a trusted, locally generated pickle (pickle can execute code).
    import pickle
    import torch
    with Path(path).open('rb') as f:
        embeddings = pickle.load(f)
    for command in instructions:
        if command not in embeddings:
            raise ValueError(f'Missing T5 embedding for exact instruction: {command!r}')
        value = embeddings[command]
        if (not isinstance(value, torch.Tensor) or tuple(value.shape) != (1, 512, 1024)
                or not torch.isfinite(value).all() or not torch.count_nonzero(value)):
            raise ValueError(f'Invalid / zero fake T5 embedding: {command!r}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('data_dir', type=Path)
    p.add_argument('--t5', type=Path)
    a = p.parse_args()
    report = check(a.data_dir)
    if a.t5:
        check_embeddings(a.t5, report['instructions'])
    print(json.dumps(report, indent=2))
    print('Structure OK. Actual Cosmos loader / model training are separate server checks.')


if __name__ == '__main__':
    main()
