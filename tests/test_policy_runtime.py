"""Inference boundary checks without loading the 2B model or requiring CUDA."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from server.policy_runtime import (
    CosmosPolicy, InferenceConfig, PolicyConfig, _load_network_state,
    _wrist_only_compatibility, consolidate_checkpoint,
)


def fake_policy(tmp_path, actions=None):
    policy = CosmosPolicy.__new__(CosmosPolicy)
    policy.config = PolicyConfig(cosmos_repo=tmp_path)
    policy.cfg = InferenceConfig()
    policy._embeddings = {"pick up the blue block on the table": np.zeros((1, 512, 1024), np.float32)}
    policy.model = object()
    policy.stats = {}
    policy._torch = SimpleNamespace(cuda=SimpleNamespace(synchronize=lambda: None))
    policy.last_inference_seconds = None
    calls = []

    def get_action(*args, **kwargs):
        calls.append((args, kwargs, Path.cwd()))
        return {"actions": np.zeros((16, 7), np.float32) if actions is None else actions}

    policy._get_action = get_action
    return policy, calls


def test_predict_uses_cached_instruction_wrist_only_and_restores_cwd(tmp_path):
    policy, calls = fake_policy(tmp_path)
    image = np.zeros((256, 256, 3), np.uint8)
    original = Path.cwd()
    actions = policy.predict(image, np.zeros(9), policy.instructions[0])
    assert actions.shape == (16, 7)
    assert actions.dtype == np.float32
    assert Path.cwd() == original
    args, kwargs, during = calls[0]
    assert during == tmp_path
    assert args[0].use_third_person_image is False
    assert args[0].use_jpeg_compression is False
    assert args[3]["wrist_image"] is image
    assert args[4] is policy._embeddings[policy.instructions[0]]
    assert kwargs["generate_future_state_and_value_in_parallel"] is False
    assert kwargs["num_denoising_steps_action"] == 5
    assert policy.last_inference_seconds >= 0


@pytest.mark.parametrize("image,state,instruction", [
    (np.zeros((224, 224, 3), np.uint8), np.zeros(9), "pick up the blue block on the table"),
    (np.zeros((256, 256, 3), np.float32), np.zeros(9), "pick up the blue block on the table"),
    (np.zeros((256, 256, 3), np.uint8), np.zeros(8), "pick up the blue block on the table"),
    (np.zeros((256, 256, 3), np.uint8), np.full(9, np.nan), "pick up the blue block on the table"),
    (np.zeros((256, 256, 3), np.uint8), np.zeros(9), "uncached instruction"),
])
def test_predict_rejects_inputs_before_inference(tmp_path, image, state, instruction):
    policy, calls = fake_policy(tmp_path)
    with pytest.raises(ValueError):
        policy.predict(image, state, instruction)
    assert calls == []


@pytest.mark.parametrize("actions", [np.zeros((15, 7)), np.full((16, 7), np.inf)])
def test_predict_rejects_invalid_actions(tmp_path, actions):
    policy, _ = fake_policy(tmp_path, actions)
    with pytest.raises(RuntimeError, match="invalid actions"):
        policy.predict(np.zeros((256, 256, 3), np.uint8), np.zeros(9), policy.instructions[0])


def test_predict_restores_cwd_when_inference_raises(tmp_path):
    policy, _ = fake_policy(tmp_path)
    original = Path.cwd()

    def fail(*args, **kwargs):
        raise RuntimeError("CUDA error")

    policy._get_action = fail
    with pytest.raises(RuntimeError, match="CUDA error"):
        policy.predict(np.zeros((256, 256, 3), np.uint8), np.zeros(9), policy.instructions[0])
    assert Path.cwd() == original


def test_consolidation_reuses_file_and_preserves_pt_symlink(tmp_path):
    blob = tmp_path / "cache-blob"
    blob.write_bytes(b"checkpoint")
    checkpoint = tmp_path / "model.pt"
    checkpoint.symlink_to(blob)
    assert consolidate_checkpoint(checkpoint) == checkpoint


def test_consolidation_requires_dcp_metadata(tmp_path):
    (tmp_path / "model").mkdir()
    with pytest.raises(FileNotFoundError, match="DCP metadata"):
        consolidate_checkpoint(tmp_path)


def test_network_loading_enforces_shapes_and_all_keys():
    import torch

    network = torch.nn.Linear(3, 2)
    model = SimpleNamespace(net=network)
    valid = {"net.weight": torch.ones((2, 3)), "net.bias": torch.ones(2)}
    assert _load_network_state(model, valid) == 2
    assert torch.equal(network.weight, valid["net.weight"])
    for invalid in (
        {"net.weight": torch.ones((3, 2)), "net.bias": torch.ones(2)},
        {"net.weight": torch.ones((2, 3))},
        dict(valid, unexpected=torch.ones(1)),
    ):
        with pytest.raises(RuntimeError, match="Checkpoint"):
            _load_network_state(model, invalid)


def test_wrist_only_compatibility_supplies_absent_indices_and_preserves_camera_branch():
    def get_action(cfg):
        if cfg.use_third_person_image:
            future_image_latent_idx = 6
            future_image2_latent_idx = 7
        return dict(future_image_latent_idx=future_image_latent_idx,
                    future_image2_latent_idx=future_image2_latent_idx)

    fixed = _wrist_only_compatibility(get_action)
    assert fixed(SimpleNamespace(use_third_person_image=False)) == {
        "future_image_latent_idx": -1, "future_image2_latent_idx": -1,
    }
    assert fixed(SimpleNamespace(use_third_person_image=True)) == {
        "future_image_latent_idx": 6, "future_image2_latent_idx": 7,
    }
    with pytest.raises(UnboundLocalError):
        get_action(SimpleNamespace(use_third_person_image=False))
    assert fixed.__globals__ is not get_action.__globals__


def test_wrist_only_compatibility_leaves_corrected_upstream_function_alone():
    def get_action(cfg):
        future_image_latent_idx = future_image2_latent_idx = -1
        return dict(future_image_latent_idx=future_image_latent_idx,
                    future_image2_latent_idx=future_image2_latent_idx)

    assert _wrist_only_compatibility(get_action) is get_action


def test_wrist_only_compatibility_rejects_unknown_source():
    def get_action(cfg):
        return {"actions": []}

    with pytest.raises(RuntimeError, match="supported wrist-only compatibility pattern"):
        _wrist_only_compatibility(get_action)
