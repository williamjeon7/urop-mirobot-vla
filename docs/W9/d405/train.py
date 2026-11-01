"""Print or launch a Cosmos Policy LIBERO fine-tuning command on a prepared GPU server."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import uuid
from pathlib import Path

import h5py

from .check_dataset import check, check_embeddings


def observation_mode(data):
    """Keep compatibility aliases out of the model's third-person input."""
    modes = set()
    files = sorted(Path(data).glob('*/*.hdf5'))
    if not files:
        raise ValueError('No HDF5 episodes found.')
    for path in files:
        with h5py.File(path, 'r') as source:
            for demo in source['data'].values():
                mode = demo.attrs.get('observation_mode', 'two_view')
                alias = bool(demo.attrs.get('agentview_is_wrist_alias', False))
                if alias and mode != 'wrist_only':
                    raise ValueError(f'{path}: wrist alias requires wrist_only observation mode.')
                if mode not in ('wrist_only', 'two_view'):
                    raise ValueError(f'{path}: unsupported observation mode {mode!r}.')
                modes.add(mode)
    if len(modes) != 1:
        raise ValueError('Do not mix wrist-only and two-view episodes in one training data root.')
    return modes.pop()


def checkpoint_file(path):
    """Keep the .pt filename: Cosmos uses its suffix to select the file reader.

    Hugging Face snapshots are symlinks to extensionless cache blobs. Resolving
    that symlink would incorrectly select the directory/DCP checkpoint reader.
    """
    return Path(os.path.abspath(Path(path).expanduser()))


def training_command(cosmos, data, checkpoint, gpus=1, batch_size=1, accum=8, steps=1000,
                     view_mode='two_view', job_name='d405_libero_finetune', smoke_proof_dir=None):
    dataset = {
        'data_dir': str(data), 't5_text_embeddings_path': str(data/'t5_embeddings.pkl'),
        'rollout_data_dir': '', 'demonstration_sampling_prob': 1.0,
        'success_rollout_sampling_prob': 0.0,
        'use_wrist_images': True, 'use_proprio': True,
        'use_third_person_images': view_mode != 'wrist_only',
    }
    overrides = [
        'experiment=cosmos_predict2_2b_480p_libero',
        'checkpoint.load_path='+json.dumps(str(checkpoint)),
        'checkpoint.load_training_state=False',
        'checkpoint.load_ema_to_reg=False',
        f'dataloader_train.batch_size={batch_size}',
        'dataloader_train.num_workers=2', f'trainer.grad_accum_iter={accum}',
        f'trainer.max_iter={steps}', 'optimizer.lr=1e-5',
        'job.group=w9_mirobot', 'job.name='+json.dumps(job_name),
        'job.wandb_mode="disabled"',
        f'model.config.fsdp_shard_size={gpus}',
    ]
    if view_mode == 'wrist_only':
        overrides += ['model.config.state_t=7', 'model.config.min_num_conditional_frames=3',
                      'model.config.max_num_conditional_frames=3',
                      'model.config.tokenizer.chunk_duration=25']
    elif view_mode != 'two_view':
        raise ValueError(f'Unsupported observation mode: {view_mode}')
    if smoke_proof_dir is not None:
        overrides += [
            '+trainer.callbacks.w9_smoke._target_="tools.w9_training_smoke.TrainingProof"',
            '+trainer.callbacks.w9_smoke.proof_dir='+json.dumps(str(smoke_proof_dir)),
            '+trainer.callbacks.w9_smoke.pretrained_checkpoint='+json.dumps(str(checkpoint)),
        ]
    # Hydra may expand these as separate LazyDicts; keep sampler and loader identical.
    for prefix in ['dataloader_train.dataset', 'dataloader_train.sampler.dataset']:
        overrides += [prefix+'.'+k+'='+json.dumps(v) for k, v in dataset.items()]
    return [sys.executable, '-m', 'torch.distributed.run', f'--nproc_per_node={gpus}',
            '--master_port=12341', '-m', 'tools.train_cosmos_libero',
            '--config=cosmos_policy/config/config.py', '--', *overrides]


def resolve_training_config(cosmos, command, report_path, env):
    """Resolve native Cosmos configuration and save primitive runtime values.

    The upstream YAML fallback stringifies LazyDict booleans; inspect the live
    configuration instead of treating that debug YAML as a runnable config.
    """
    code = '''
import json, sys
from pathlib import Path
from cosmos_policy._src.imaginaire.config import load_config
c = load_config('cosmos_policy/config/config.py', ['--', *sys.argv[2:]], enable_one_logger=True)
d = c.dataloader_train.dataset
s = c.dataloader_train.sampler.dataset
assert type(d.use_third_person_images) is bool
assert type(s.use_third_person_images) is bool
mode = 'two_view' if d.use_third_person_images else 'wrist_only'
expected = (9, 4, 33) if mode == 'two_view' else (7, 3, 25)
assert (c.model.config.state_t, c.model.config.min_num_conditional_frames, c.model.config.tokenizer.chunk_duration) == expected
assert c.model.config.max_num_conditional_frames == expected[1]
assert d.use_third_person_images == s.use_third_person_images
assert d.data_dir == s.data_dir and d.t5_text_embeddings_path == s.t5_text_embeddings_path
result = dict(status='passed', source='actual Cosmos load_config runtime values', observation_mode=mode,
              state_t=c.model.config.state_t, conditioning_frames=c.model.config.min_num_conditional_frames,
              chunk_duration=c.model.config.tokenizer.chunk_duration, fsdp_shard_size=c.model.config.fsdp_shard_size,
              third_person_input=d.use_third_person_images, max_iter=c.trainer.max_iter,
              data_dir=d.data_dir, t5_path=d.t5_text_embeddings_path, model_checkpoint=c.checkpoint.load_path,
              output_dir=c.job.path_local)
Path(sys.argv[1]).write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
'''
    report_path.parent.mkdir(parents=True, exist_ok=True)
    overrides = command[command.index('--') + 1:]
    subprocess.run([sys.executable, '-c', code, str(report_path), *overrides],
                   cwd=cosmos, env=env, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cosmos-repo', type=Path, required=True)
    p.add_argument('--data-dir', type=Path, required=True)
    p.add_argument('--checkpoint', type=Path, required=True, help='Local LIBERO Policy .pt, not a base Video2World checkpoint')
    p.add_argument('--gpus', type=int, default=1)
    p.add_argument('--batch-size', type=int, default=1)
    p.add_argument('--accum', type=int, default=8)
    p.add_argument('--steps', type=int, default=1000)
    p.add_argument('--job-name', default='d405_libero_finetune', help='Separate smoke-run output from a fine-tuning run')
    p.add_argument('--run', action='store_true', help='Actually launch GPU training; default prints only')
    p.add_argument('--dryrun', action='store_true', help='Resolve the actual Cosmos training configuration without training')
    p.add_argument('--config-report', type=Path, help='JSON output for --dryrun; defaults to <data-dir>/training_config_validation.json')
    p.add_argument('--smoke', action='store_true', help='Run one native optimizer update and save finite loss/gradient evidence')
    p.add_argument('--smoke-report', type=Path, help='Defaults to <data-dir>/training_smoke.json')
    a = p.parse_args()
    if a.smoke and (not a.run or a.dryrun):
        p.error('--smoke requires --run and cannot be combined with --dryrun.')
    if min(a.gpus, a.batch_size, a.accum, a.steps) < 1:
        p.error('GPU count, batch size, accumulation, steps must be positive.')
    cosmos, data, ckpt = a.cosmos_repo.resolve(), a.data_dir.resolve(), checkpoint_file(a.checkpoint)
    proof_dir = None
    smoke_report = None
    if a.smoke:
        a.steps, a.accum = 1, 1
        run_id = uuid.uuid4().hex[:12]
        if a.job_name == 'd405_libero_finetune':
            a.job_name = 'd405_libero_smoke_'+run_id
        smoke_report = (a.smoke_report or data/'training_smoke.json').resolve()
        proof_dir = smoke_report.parent/'training_smoke_runs'/run_id
    report = check(data)
    mode = observation_mode(data)
    cmd = training_command(cosmos, data, ckpt, a.gpus, a.batch_size, a.accum, a.steps, mode, a.job_name, proof_dir)
    print('Working directory:', cosmos)
    print('Train data:', json.dumps(report, indent=2))
    print('Observation mode:', mode)
    print(shlex.join(cmd))
    print('Initial settings are a smoke-run starting point, not a validated training recipe.')
    if not (a.run or a.dryrun):
        return
    if sys.platform == 'win32':
        p.error('Launch training in the prepared Linux GPU Cosmos environment.')
    if not (cosmos/'cosmos_policy/scripts/train.py').is_file() or not ckpt.is_file():
        p.error('Cosmos checkout or local LIBERO checkpoint is missing.')
    check_embeddings(data/'t5_embeddings.pkl', report['instructions'])
    stats = data/'dataset_statistics.json'
    if not stats.is_file() or stats.stat().st_mtime < max(f.stat().st_mtime for f in data.glob('*/*.hdf5')):
        p.error('Run tools.check_cosmos_dataset --statistics <official LIBERO statistics.json> first; statistics missing or stale.')
    env = os.environ.copy()
    root = Path(__file__).resolve().parents[3]
    env['PYTHONPATH'] = os.pathsep.join([str(cosmos), str(root), env.get('PYTHONPATH', '')])
    env.setdefault('WANDB_MODE', 'offline')
    env.setdefault('IMAGINAIRE_OUTPUT_ROOT', str(root/'outputs'))
    print('Training output root:', env['IMAGINAIRE_OUTPUT_ROOT'])
    if a.dryrun:
        resolve_training_config(cosmos, cmd, (a.config_report or data/'training_config_validation.json').resolve(), env)
        return
    try:
        subprocess.run(cmd, cwd=cosmos, env=env, check=True)
        if a.smoke:
            ranks = [json.loads((proof_dir/f'rank{rank}.json').read_text(encoding='utf-8'))
                     for rank in range(a.gpus)]
            if not all(r['status'] == 'passed' and r['optimizer_steps'] == 1 and
                       r.get('pretrained_checkpoint_loaded') for r in ranks):
                raise ValueError('Not all training ranks completed the native optimizer step.')
            result = dict(status='passed', source='native Cosmos trainer with observation-only proof callbacks',
                          gpus=a.gpus, optimizer_steps=1, grad_accum_iter=1,
                          real_t5=True, observation_mode=mode, checkpoint=str(ckpt),
                          pretrained_checkpoint_loaded=True,
                          data_dir=str(data), proof_dir=str(proof_dir), ranks=ranks)
            smoke_report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    except Exception as error:
        if a.smoke:
            smoke_report.write_text(json.dumps(dict(status='failed', error=f'{type(error).__name__}: {error}',
                                                   proof_dir=str(proof_dir)), indent=2), encoding='utf-8')
        raise


if __name__ == '__main__':
    main()
