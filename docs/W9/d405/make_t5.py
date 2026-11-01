"""Build real T5-11B instruction embeddings on the GPU server (large model).

Use the same encoder family as Cosmos Policy. Downloads are opt-in.
"""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

from .check_dataset import check


def encode_commands(tokenizer, model, commands, device):
    """Match CosmosT5TextEncoder, including zero padding after the EOS token."""
    import torch
    embeddings = {}
    with torch.inference_mode():
        for command in commands:
            tokens = tokenizer(command, padding='max_length', truncation=True, max_length=512,
                               return_tensors='pt').to(device)
            value = model(input_ids=tokens.input_ids, attention_mask=tokens.attention_mask).last_hidden_state
            if tuple(value.shape) != (1, 512, 1024):
                raise ValueError(f'Unexpected T5 output shape: {value.shape}')
            value = value.masked_fill(~tokens.attention_mask.bool().unsqueeze(-1), 0)
            if not torch.isfinite(value).all() or not torch.count_nonzero(value):
                raise ValueError(f'Invalid T5 output for {command!r}')
            embeddings[command] = value.to(dtype=torch.bfloat16, device='cpu')
            print('Encoded:', command, flush=True)
    return embeddings


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('data_dir', type=Path)
    p.add_argument('--model', default='google-t5/t5-11b', help='Hugging Face model ID or local model directory')
    p.add_argument('--allow-download', action='store_true', help='Allow fetching the large T5-11B model')
    p.add_argument('--device', default='cuda')
    p.add_argument('--instruction', action='append', help='Prepare this exact instruction before HDF5 exists; repeatable')
    p.add_argument('--dtype', choices=['float32', 'bfloat16'], default='float32',
                   help='Encoder precision; float32 matches the upstream Cosmos generator')
    a = p.parse_args()
    commands = sorted(set(a.instruction)) if a.instruction else check(a.data_dir)['instructions']
    if any(not command.strip() or command != command.strip() for command in commands):
        p.error('Instructions must be nonempty without leading/trailing whitespace.')
    out = a.data_dir/'t5_embeddings.pkl'
    if out.exists():
        raise FileExistsError(f'{out} already exists; retain or move it before regenerating.')
    import torch
    from transformers import T5EncoderModel, T5TokenizerFast
    local = not a.allow_download
    tokenizer = T5TokenizerFast.from_pretrained(a.model, local_files_only=local)
    model = T5EncoderModel.from_pretrained(a.model, local_files_only=local,
                                           torch_dtype=getattr(torch, a.dtype), low_cpu_mem_usage=True).to(a.device).eval()
    embeddings = encode_commands(tokenizer, model, commands, a.device)
    a.data_dir.mkdir(parents=True, exist_ok=True)
    with out.open('xb') as f:
        pickle.dump(embeddings, f)
    print('Wrote:', out)


if __name__ == '__main__':
    main()
