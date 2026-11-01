"""Runtime evidence from an actual Cosmos forward/backward/optimizer step."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path

import torch

from cosmos_policy._src.imaginaire.utils.callback import Callback
from cosmos_policy._src.imaginaire.utils.misc import get_local_tensor_if_DTensor


def verify_pretrained_weights(model, checkpoint, keys=None):
    """Compare nontrivial model tensors to the released checkpoint before training."""
    source = torch.load(checkpoint, map_location='cpu', weights_only=True, mmap=True)
    if 'model' in source:
        source = source['model']
    elif 'state_dict' in source:
        source = source['state_dict']
    # PyTorch activation-checkpoint wrappers are transparent in state_dict names.
    # named_parameters retains this wrapper component after FSDP is applied.
    parameters = {}
    for name, value in model.named_parameters():
        canonical = name.replace('._checkpoint_wrapped_module.', '.').replace('._fsdp_wrapped_module.', '.')
        if canonical in parameters:
            raise ValueError(f'Ambiguous model parameter after removing checkpoint wrappers: {canonical}')
        parameters[canonical] = value
    required = {name: value for name, value in parameters.items() if value.requires_grad}
    for name, value in required.items():
        if name not in source or tuple(source[name].shape) != tuple(value.shape):
            raise ValueError(f'Pretrained checkpoint is missing or has a wrong shape for {name}')
    if keys is None:
        keys = ['net.x_embedder.proj.1.weight', 'net.blocks.0.self_attn.q_proj.weight',
                'net.final_layer.linear.weight']
    samples = []
    for name in keys:
        actual = parameters[name].detach()
        if hasattr(actual, 'full_tensor'):
            actual = actual.full_tensor()  # Every rank participates in the same gathers.
        actual = actual.cpu().contiguous()
        expected = source[name].to(dtype=actual.dtype).contiguous()
        if not torch.equal(actual, expected):
            raise ValueError(f'Model weights do not match the pretrained LIBERO checkpoint: {name}')
        digest = hashlib.sha256(actual.view(torch.uint8).numpy().tobytes()).hexdigest()
        samples.append(dict(name=name, shape=list(actual.shape), dtype=str(actual.dtype), sha256=digest))
    return dict(checkpoint=str(checkpoint), parameter_shapes_checked=len(required), tensors=samples)


class TrainingProof(Callback):
    """Observe native training hooks without changing its loss or optimizer."""

    def __init__(self, proof_dir, pretrained_checkpoint=None):
        super().__init__()
        self.proof_dir = Path(proof_dir)
        self.losses = []
        self.backward_passes = 0
        self.optimizer_steps = 0
        self.nonzero_gradient_tensors = 0
        self.max_gradient_abs = 0.0
        self.model_video_shape = None
        self.pretrained_checkpoint = pretrained_checkpoint
        self.pretrained_proof = None

    def on_train_start(self, model, iteration=0):
        if iteration != 0 or self.pretrained_checkpoint is None:
            raise ValueError('Smoke verification requires a fresh, pretrained checkpoint initialization.')
        self.pretrained_proof = verify_pretrained_weights(model, self.pretrained_checkpoint)
        print('W9_PRETRAINED_WEIGHTS_VERIFIED '+json.dumps(self.pretrained_proof), flush=True)

    def on_training_step_batch_start(self, model, data, iteration=0):
        self.model_video_shape = list(data['video'].shape)

    def on_before_backward(self, model_ddp, loss, iteration=0):
        value = loss.detach()
        if value.numel() != 1 or not torch.isfinite(value).all():
            raise ValueError('The native Cosmos training loss is not a finite scalar.')
        self.losses.append(float(value.cpu()))

    def on_after_backward(self, model_ddp, iteration=0):
        nonzero = 0
        maximum = 0.0
        for parameter in model_ddp.parameters():
            if parameter.grad is None:
                continue
            gradient = get_local_tensor_if_DTensor(parameter.grad.detach())
            if not torch.isfinite(gradient).all():
                raise ValueError('The native Cosmos backward pass produced a non-finite gradient.')
            if gradient.numel():
                absolute = float(gradient.abs().max().cpu())
                maximum = max(maximum, absolute)
                nonzero += int(absolute > 0)
        if not nonzero:
            raise ValueError('The native Cosmos backward pass produced no nonzero gradients on this rank.')
        self.backward_passes += 1
        self.nonzero_gradient_tensors += nonzero
        self.max_gradient_abs = max(self.max_gradient_abs, maximum)

    def on_before_zero_grad(self, model_ddp, optimizer, scheduler, iteration=0):
        # This hook follows grad_scaler.step and scheduler.step in the native trainer.
        self.optimizer_steps += 1

    def on_train_end(self, model, iteration=0):
        if iteration != 1 or self.optimizer_steps != 1 or self.backward_passes != 1:
            raise ValueError('The smoke run must complete exactly one native optimizer iteration.')
        if self.pretrained_proof is None:
            raise ValueError('The smoke run did not verify its pretrained checkpoint weights.')
        rank = int(os.environ.get('RANK', '0'))
        report = dict(status='passed', rank=rank, completed_iteration=iteration,
                      loss_values=self.losses, backward_passes=self.backward_passes,
                      optimizer_steps=self.optimizer_steps,
                      nonzero_gradient_tensors=self.nonzero_gradient_tensors,
                      max_gradient_abs=self.max_gradient_abs,
                      batch_video_shape=self.model_video_shape,
                      pretrained_checkpoint_loaded=self.pretrained_proof is not None,
                      pretrained_weight_proof=self.pretrained_proof,
                      peak_allocated_cuda_bytes=torch.cuda.max_memory_allocated(),
                      peak_reserved_cuda_bytes=torch.cuda.max_memory_reserved())
        self.proof_dir.mkdir(parents=True, exist_ok=True)
        (self.proof_dir/f'rank{rank}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('W9_NATIVE_TRAINING_PROOF '+json.dumps(report), flush=True)
