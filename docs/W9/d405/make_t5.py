"""Build real T5-11B instruction embeddings on the GPU server (large model).

Use the same encoder family as Cosmos Policy. Downloads are opt-in.
"""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

from .check_dataset import check


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('data_dir', type=Path)
    p.add_argument('--model', default='google-t5/t5-11b', help='Hugging Face model ID or local model directory')
    p.add_argument('--allow-download', action='store_true', help='Allow fetching the large T5-11B model')
    p.add_argument('--device', default='cuda')
    a = p.parse_args()
    report = check(a.data_dir)
    out = a.data_dir/'t5_embeddings.pkl'
    if out.exists():
        raise FileExistsError(f'{out} already exists; retain or move it before regenerating.')
    import torch
    from transformers import T5EncoderModel, T5Tokenizer
    local = not a.allow_download
    tokenizer = T5Tokenizer.from_pretrained(a.model, local_files_only=local)
    model = T5EncoderModel.from_pretrained(a.model, local_files_only=local,
                                           torch_dtype=torch.bfloat16).to(a.device).eval()
    embeddings = {}
    with torch.inference_mode():
        for command in report['instructions']:
            tokens = tokenizer(command, padding='max_length', truncation=True, max_length=512,
                               return_tensors='pt').to(a.device)
            value = model(input_ids=tokens.input_ids, attention_mask=tokens.attention_mask).last_hidden_state
            if tuple(value.shape) != (1, 512, 1024):
                raise ValueError(f'Unexpected T5 output shape: {value.shape}')
            embeddings[command] = value.to(dtype=torch.bfloat16, device='cpu')
            print('Encoded:', command)
    with out.open('xb') as f:
        pickle.dump(embeddings, f)
    print('Wrote:', out)


if __name__ == '__main__':
    main()
