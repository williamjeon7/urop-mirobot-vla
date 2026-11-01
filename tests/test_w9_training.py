"""Wrist-only data must never activate the compatibility third-person alias."""
from pathlib import Path

import h5py
import numpy as np
import pytest
import torch

from docs.W9.d405.train import checkpoint_file, observation_mode, training_command
from tools.check_cosmos_dataset import verify_sample
from tools.w9_training_smoke import TrainingProof, verify_pretrained_weights


def episode(root, name='episode', mode='wrist_only', alias=True):
    suite = root/'mirobot_real'
    suite.mkdir(exist_ok=True)
    with h5py.File(suite/f'{name}.hdf5', 'w') as output:
        demo = output.create_group('data/demo_0')
        if mode is not None:
            demo.attrs['observation_mode'] = mode
        demo.attrs['agentview_is_wrist_alias'] = alias


def test_camera_mode_detects_real_wrist_and_legacy_two_view(tmp_path):
    episode(tmp_path)
    assert observation_mode(tmp_path) == 'wrist_only'
    with h5py.File(tmp_path/'mirobot_real/episode.hdf5', 'a') as output:
        demo = output['data/demo_0']
        del demo.attrs['observation_mode']
        demo.attrs['agentview_is_wrist_alias'] = False
    assert observation_mode(tmp_path) == 'two_view'


def test_alias_cannot_be_enabled_as_a_third_person_camera(tmp_path):
    episode(tmp_path, mode='two_view', alias=True)
    with pytest.raises(ValueError, match='wrist alias'):
        observation_mode(tmp_path)


def test_mixed_camera_modes_are_rejected(tmp_path):
    episode(tmp_path)
    episode(tmp_path, name='second', mode='two_view', alias=False)
    with pytest.raises(ValueError, match='mix'):
        observation_mode(tmp_path)


def test_wrist_training_overrides_model_layout_and_both_dataset_references():
    command = training_command(Path('/cosmos'), Path('/data'), Path('/checkpoint.pt'),
                               gpus=4, view_mode='wrist_only')
    for prefix in ['dataloader_train.dataset', 'dataloader_train.sampler.dataset']:
        assert prefix+'.use_third_person_images=false' in command
        assert prefix+'.use_wrist_images=true' in command
        assert prefix+'.use_proprio=true' in command
    for value in ['model.config.state_t=7', 'model.config.min_num_conditional_frames=3',
                  'model.config.max_num_conditional_frames=3',
                  'model.config.tokenizer.chunk_duration=25', 'model.config.fsdp_shard_size=4']:
        assert value in command
    assert 'tools.train_cosmos_libero' in command
    assert 'job.wandb_mode="disabled"' in command


def test_huggingface_checkpoint_symlink_keeps_pt_file_reader(tmp_path):
    blob = tmp_path/'blobs'/'8818528d8c9150cda0ddf8c711b0f221b21dac8ac379bd26d5690235954d33e2'
    blob.parent.mkdir()
    blob.write_bytes(b'cached checkpoint')
    snapshot = tmp_path/'snapshots'/'commit'/'Cosmos-Policy-LIBERO-Predict2-2B.pt'
    snapshot.parent.mkdir(parents=True)
    snapshot.symlink_to(blob)
    selected = checkpoint_file(snapshot)
    assert selected.is_file()
    assert selected.name.endswith('.pt')
    assert selected != selected.resolve()
    assert selected.resolve() == blob


def test_training_cli_passes_snapshot_pt_filename_to_native_command(tmp_path, monkeypatch, capsys):
    from docs.W9.d405 import train as train_module
    blob = tmp_path/'cache'/'extensionless_blob'
    blob.parent.mkdir()
    blob.write_bytes(b'checkpoint')
    snapshot = tmp_path/'snapshot'/'Cosmos-Policy-LIBERO-Predict2-2B.pt'
    snapshot.parent.mkdir()
    snapshot.symlink_to(blob)
    monkeypatch.setattr(train_module, 'check', lambda path: {'instructions': ['pick up the blue block on the table']})
    monkeypatch.setattr(train_module, 'observation_mode', lambda path: 'wrist_only')
    monkeypatch.setattr('sys.argv', ['train', '--cosmos-repo', str(tmp_path/'cosmos'),
                                   '--data-dir', str(tmp_path/'data'), '--checkpoint', str(snapshot)])
    train_module.main()
    output = capsys.readouterr().out
    assert str(snapshot) in output
    assert str(blob) not in output
    assert 'tools.train_cosmos_libero' in output


@pytest.mark.parametrize('configured_root', [None, '/mnt/custom-training-output'])
def test_training_cli_saves_on_workspace_disk_and_respects_output_override(tmp_path, monkeypatch, configured_root):
    from docs.W9.d405 import train as train_module
    cosmos = tmp_path/'cosmos'
    native_entrypoint = cosmos/'cosmos_policy/scripts/train.py'
    native_entrypoint.parent.mkdir(parents=True)
    native_entrypoint.touch()
    checkpoint = tmp_path/'checkpoint.pt'
    checkpoint.touch()
    data = tmp_path/'data'
    data.mkdir()
    episode(data)
    (data/'dataset_statistics.json').write_text('{}')
    monkeypatch.setattr(train_module, 'check', lambda path: {'instructions': ['pick up the blue block on the table']})
    monkeypatch.setattr(train_module, 'check_embeddings', lambda *args: None)
    monkeypatch.setattr(train_module, 'observation_mode', lambda path: 'wrist_only')
    if configured_root is None:
        monkeypatch.delenv('IMAGINAIRE_OUTPUT_ROOT', raising=False)
    else:
        monkeypatch.setenv('IMAGINAIRE_OUTPUT_ROOT', configured_root)
    resolved = {}
    monkeypatch.setattr(train_module, 'resolve_training_config',
                        lambda cosmos, command, report, env: resolved.update(env))
    monkeypatch.setattr('sys.argv', ['train', '--cosmos-repo', str(cosmos),
                                   '--data-dir', str(data), '--checkpoint', str(checkpoint), '--dryrun'])
    train_module.main()
    expected = configured_root or str(Path(train_module.__file__).resolve().parents[3]/'outputs')
    assert resolved['IMAGINAIRE_OUTPUT_ROOT'] == expected


def sample():
    return dict(video=torch.zeros(3, 25, 224, 224, dtype=torch.uint8),
                actions=np.zeros((16, 7), dtype=np.float32),
                t5_text_embeddings=torch.ones(512, 1024, dtype=torch.bfloat16),
                current_image_latent_idx=-1, future_image_latent_idx=-1,
                proprio=np.zeros(9, dtype=np.float32))


def test_valid_single_camera_model_sample():
    verify_sample(sample(), 'wrist_only', True)


@pytest.mark.parametrize('key', ['actions', 'proprio', 't5_text_embeddings'])
def test_nonfinite_training_fields_are_rejected(key):
    value = sample()
    value[key].reshape(-1)[0] = float('nan')
    with pytest.raises(ValueError, match='Non-finite'):
        verify_sample(value, 'wrist_only', True)


def test_zero_t5_does_not_pass_as_real_embeddings():
    value = sample()
    value['t5_text_embeddings'].zero_()
    with pytest.raises(ValueError, match='all zero'):
        verify_sample(value, 'wrist_only', True)


def test_wrong_camera_latent_index_and_video_layout_are_rejected():
    value = sample()
    value['current_image_latent_idx'] = 3
    with pytest.raises(ValueError, match='third-person'):
        verify_sample(value, 'wrist_only', True)
    value = sample()
    value['video'] = torch.zeros(3, 33, 224, 224, dtype=torch.uint8)
    with pytest.raises(ValueError, match='video shape'):
        verify_sample(value, 'wrist_only', True)


def test_smoke_callback_rejects_nonfinite_loss_and_gradients(tmp_path):
    proof = TrainingProof(tmp_path)
    model = torch.nn.Linear(2, 1)
    with pytest.raises(ValueError, match='finite scalar'):
        proof.on_before_backward(model, torch.tensor(float('nan')))
    with pytest.raises(ValueError, match='no nonzero gradients'):
        proof.on_after_backward(model)
    model.weight.grad = torch.full_like(model.weight, float('nan'))
    with pytest.raises(ValueError, match='non-finite gradient'):
        proof.on_after_backward(model)


def test_smoke_callback_only_records_completed_optimizer_step(tmp_path, monkeypatch):
    proof = TrainingProof(tmp_path)
    model = torch.nn.Linear(2, 1)
    proof.on_training_step_batch_start(model, {'video': torch.zeros(1, 3, 25, 224, 224)})
    value = model(torch.ones(1, 2)).square().mean()
    proof.on_before_backward(model, value)
    value.backward()
    proof.on_after_backward(model)
    with pytest.raises(ValueError, match='exactly one'):
        proof.on_train_end(model, iteration=1)
    proof.on_before_zero_grad(model, None, None)
    checkpoint = tmp_path/'model.pt'
    torch.save(model.state_dict(), checkpoint)
    proof.pretrained_proof = verify_pretrained_weights(model, checkpoint, keys=['weight', 'bias'])
    monkeypatch.setattr(torch.cuda, 'max_memory_allocated', lambda: 0)
    monkeypatch.setattr(torch.cuda, 'max_memory_reserved', lambda: 0)
    monkeypatch.setenv('RANK', '0')
    proof.on_train_end(model, iteration=1)
    import json
    report = json.loads((tmp_path/'rank0.json').read_text())
    assert report['status'] == 'passed'
    assert report['optimizer_steps'] == 1
    assert report['backward_passes'] == 1
    assert report['nonzero_gradient_tensors'] > 0
    assert report['batch_video_shape'] == [1, 3, 25, 224, 224]
    assert report['pretrained_checkpoint_loaded']


def test_pretrained_proof_detects_random_or_changed_weights(tmp_path):
    model = torch.nn.Linear(2, 1)
    checkpoint = tmp_path/'released.pt'
    torch.save(model.state_dict(), checkpoint)
    proof = verify_pretrained_weights(model, checkpoint, keys=['weight', 'bias'])
    assert proof['parameter_shapes_checked'] == 2
    with torch.no_grad():
        model.weight.add_(1)
    with pytest.raises(ValueError, match='do not match'):
        verify_pretrained_weights(model, checkpoint, keys=['weight', 'bias'])


def test_pretrained_proof_handles_native_activation_checkpoint_wrappers(tmp_path):
    model = torch.nn.Module()
    model.block = torch.nn.Module()
    model.block._checkpoint_wrapped_module = torch.nn.Linear(2, 1)
    checkpoint = tmp_path/'wrapped.pt'
    torch.save({'block.weight': model.block._checkpoint_wrapped_module.weight.detach(),
                'block.bias': model.block._checkpoint_wrapped_module.bias.detach()}, checkpoint)
    proof = verify_pretrained_weights(model, checkpoint, keys=['block.weight', 'block.bias'])
    assert proof['parameter_shapes_checked'] == 2


def test_pretrained_proof_rejects_ambiguous_wrapper_names(tmp_path):
    model = torch.nn.Module()
    model.block = torch.nn.Module()
    model.block.weight = torch.nn.Parameter(torch.ones(1, 2))
    model.block._checkpoint_wrapped_module = torch.nn.Linear(2, 1)
    checkpoint = tmp_path/'ambiguous.pt'
    torch.save({}, checkpoint)
    with pytest.raises(ValueError, match='Ambiguous model parameter'):
        verify_pretrained_weights(model, checkpoint, keys=['block.weight'])
