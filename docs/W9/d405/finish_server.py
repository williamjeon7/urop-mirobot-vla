"""Build and verify real Mirobot demonstrations for Cosmos Policy LIBERO."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from .check_dataset import check, check_embeddings
from .train import checkpoint_file
from .capture_storage import resolve_blue_episode

ROOT = Path(__file__).resolve().parents[3]
POLICY = 'nvidia/Cosmos-Policy-LIBERO-Predict2-2B'


def cached_policy_file(name, allow_download):
    from huggingface_hub import hf_hub_download
    return Path(hf_hub_download(POLICY, name, local_files_only=not allow_download))


def run(command, log, env):
    print('$ '+shlex.join(map(str, command)), flush=True)
    with log.open('w', encoding='utf-8') as output:
        output.write('$ '+shlex.join(map(str, command))+'\n')
        output.flush()
        process = subprocess.Popen(list(map(str, command)), cwd=ROOT, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1)
        for line in process.stdout:
            print(line, end='', flush=True)
            output.write(line)
            output.flush()
        code = process.wait()
    if code:
        raise RuntimeError(f'Command failed ({code}); see {log}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episodes', nargs='+', type=Path,
                        default=[resolve_blue_episode(ROOT/'docs/W9/data/raw', n) for n in range(1, 11)])
    parser.add_argument('--data-dir', type=Path, default=ROOT/'docs/W9/data/hdf5')
    parser.add_argument('--target', choices=['red', 'green', 'blue'], required=True)
    parser.add_argument('--real-success', action='store_true', help='Confirm these real recordings achieved the reviewed target')
    parser.add_argument('--allow-download', action='store_true', help='Fetch missing official T5 / policy assets')
    parser.add_argument('--statistics', type=Path)
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--t5-model', default='google-t5/t5-11b')
    parser.add_argument('--gpus', type=int, default=4)
    parser.add_argument('--smoke', action='store_true', help='Also verify one native forward/backward/optimizer iteration')
    args = parser.parse_args()
    if not args.real_success:
        parser.error('Confirm the real pickup with --real-success after reviewing the recordings.')
    if args.gpus < 1:
        parser.error('--gpus must be positive.')
    data = args.data_dir.resolve()
    data.mkdir(parents=True, exist_ok=True)
    logs = data/'validation_logs'
    logs.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(OPENBLAS_NUM_THREADS='2', OMP_NUM_THREADS='2', PYTHONUNBUFFERED='1')
    report_path = data/'ready.json'
    result = dict(status='running', target=args.target,
                  instruction=f'pick up the {args.target} block on the table',
                  observation_mode='wrist_only', timestep_s=.05,
                  training_started=False)
    report_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    try:
        run([sys.executable, '-m', 'docs.W9.d405.export_real_hdf5',
             *[p.resolve() for p in args.episodes], '--out', data/'mirobot_real',
             '--target', args.target, '--real-success', '--skip-existing'],
            logs/'export.log', env)
        structure = check(data)
        expected = f'pick up the {args.target} block on the table'
        if structure['episodes'] != len(args.episodes) or structure['instructions'] != [expected]:
            raise ValueError(f'Dataset episode count or instructions differ from the requested batch: {structure}')
        t5 = data/'t5_embeddings.pkl'
        if t5.exists():
            check_embeddings(t5, structure['instructions'])
            print('Existing real T5 embeddings validated.', flush=True)
        else:
            command = [sys.executable, '-m', 'docs.W9.d405.make_t5', data, '--model', args.t5_model]
            if args.allow_download:
                command.append('--allow-download')
            run(command, logs/'t5.log', env)
        statistics = (args.statistics.resolve() if args.statistics else
                      cached_policy_file('libero_dataset_statistics.json', args.allow_download))
        checkpoint = (checkpoint_file(args.checkpoint) if args.checkpoint else
                      cached_policy_file('Cosmos-Policy-LIBERO-Predict2-2B.pt', args.allow_download))
        run([sys.executable, '-m', 'docs.W9.d405.check_dataset', data, '--t5', t5],
            logs/'structure.log', env)
        run([sys.executable, '-m', 'tools.check_cosmos_dataset', '--data-dir', data,
             '--t5', t5, '--statistics', statistics, '--report', data/'loader_validation.json'],
            logs/'loader.log', env)
        loader = json.loads((data/'loader_validation.json').read_text(encoding='utf-8'))
        if not loader.get('training_ready'):
            raise ValueError('Real Cosmos loader did not confirm training readiness.')
        run([sys.executable, '-m', 'docs.W9.d405.train', '--cosmos-repo', ROOT/'cosmos-policy',
             '--data-dir', data, '--checkpoint', checkpoint, '--gpus', args.gpus,
             '--dryrun', '--config-report', data/'training_config_validation.json'],
            logs/'train_command.log', env)
        if args.smoke:
            result['training_started'] = True
            run([sys.executable, '-m', 'docs.W9.d405.train', '--cosmos-repo', ROOT/'cosmos-policy',
                 '--data-dir', data, '--checkpoint', checkpoint, '--gpus', args.gpus,
                 '--run', '--smoke'], logs/'smoke.log', env)
            smoke_report = json.loads((data/'training_smoke.json').read_text(encoding='utf-8'))
            if (smoke_report.get('status') != 'passed' or
                    smoke_report.get('pretrained_checkpoint_loaded') is not True):
                raise ValueError('Native GPU training validation did not pass.')
            result['training_smoke_report'] = str(data/'training_smoke.json')
        result.update(status='ready', structure=structure, loader_report=str(data/'loader_validation.json'),
                      t5_embeddings=str(t5), statistics=str(data/'dataset_statistics.json'),
                      checkpoint=str(checkpoint), train_command_log=str(logs/'train_command.log'))
    except Exception as error:
        result.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
