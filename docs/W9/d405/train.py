"""Print or launch a Cosmos Policy LIBERO fine-tuning command on a prepared GPU server."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from .check_dataset import check, check_embeddings


def training_command(cosmos, data, checkpoint, gpus=1, batch_size=1, accum=8, steps=1000):
    dataset = {
        'data_dir': str(data), 't5_text_embeddings_path': str(data/'t5_embeddings.pkl'),
        'rollout_data_dir': '', 'demonstration_sampling_prob': 1.0,
        'success_rollout_sampling_prob': 0.0,
    }
    overrides = [
        'experiment=cosmos_predict2_2b_480p_libero',
        'checkpoint.load_path='+json.dumps(str(checkpoint)),
        'checkpoint.load_training_state=False',
        'checkpoint.load_ema_to_reg=False',
        f'dataloader_train.batch_size={batch_size}',
        'dataloader_train.num_workers=2', f'trainer.grad_accum_iter={accum}',
        f'trainer.max_iter={steps}', 'optimizer.lr=1e-5',
        'job.group=w9_mirobot', 'job.name=d405_libero_finetune',
    ]
    # Hydra may expand these as separate LazyDicts; keep sampler and loader identical.
    for prefix in ['dataloader_train.dataset', 'dataloader_train.sampler.dataset']:
        overrides += [prefix+'.'+k+'='+json.dumps(v) for k, v in dataset.items()]
    return [sys.executable, '-m', 'torch.distributed.run', f'--nproc_per_node={gpus}',
            '--master_port=12341', '-m', 'cosmos_policy.scripts.train',
            '--config=cosmos_policy/config/config.py', '--', *overrides]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cosmos-repo', type=Path, required=True)
    p.add_argument('--data-dir', type=Path, required=True)
    p.add_argument('--checkpoint', type=Path, required=True, help='Local LIBERO Policy .pt, not a base Video2World checkpoint')
    p.add_argument('--gpus', type=int, default=1)
    p.add_argument('--batch-size', type=int, default=1)
    p.add_argument('--accum', type=int, default=8)
    p.add_argument('--steps', type=int, default=1000)
    p.add_argument('--run', action='store_true', help='Actually launch GPU training; default prints only')
    a = p.parse_args()
    if min(a.gpus, a.batch_size, a.accum, a.steps) < 1:
        p.error('GPU count, batch size, accumulation, steps must be positive.')
    cosmos, data, ckpt = a.cosmos_repo.resolve(), a.data_dir.resolve(), a.checkpoint.resolve()
    report = check(data)
    cmd = training_command(cosmos, data, ckpt, a.gpus, a.batch_size, a.accum, a.steps)
    print('Working directory:', cosmos)
    print('Train data:', json.dumps(report, indent=2))
    print(shlex.join(cmd))
    print('Initial settings are a smoke-run starting point, not a validated training recipe.')
    if not a.run:
        return
    if sys.platform == 'win32':
        p.error('Launch training in the prepared Linux GPU Cosmos environment.')
    if not (cosmos/'cosmos_policy/scripts/train.py').is_file() or not ckpt.is_file():
        p.error('Cosmos checkout or local LIBERO checkpoint is missing.')
    check_embeddings(data/'t5_embeddings.pkl', report['instructions'])
    stats = data/'dataset_statistics.json'
    if not stats.is_file() or stats.stat().st_mtime < max(f.stat().st_mtime for f in data.glob('*/*.hdf5')):
        p.error('Run tools.check_cosmos_dataset --recompute-stats first; statistics missing or stale.')
    env = os.environ.copy()
    env['PYTHONPATH'] = str(cosmos) + os.pathsep + env.get('PYTHONPATH', '')
    subprocess.run(cmd, cwd=cosmos, env=env, check=True)


if __name__ == '__main__':
    main()
