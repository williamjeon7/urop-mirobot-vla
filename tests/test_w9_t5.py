from types import SimpleNamespace

import pytest
import torch
from transformers import BatchEncoding

from docs.W9.d405.make_t5 import encode_commands


class Tokenizer:
    def __call__(self, command, **kwargs):
        assert command == 'pick up the blue block on the table'
        assert kwargs['max_length'] == 512
        mask = torch.zeros(1, 512, dtype=torch.long)
        mask[:, :10] = 1
        return BatchEncoding(dict(input_ids=torch.ones_like(mask), attention_mask=mask))


def test_t5_padding_matches_upstream_cosmos():
    value = torch.arange(512 * 1024, dtype=torch.float32).reshape(1, 512, 1024) / 1024
    model = lambda **kwargs: SimpleNamespace(last_hidden_state=value)
    command = 'pick up the blue block on the table'
    result = encode_commands(Tokenizer(), model, [command], 'cpu')[command]
    assert result.dtype == torch.bfloat16
    assert result.device.type == 'cpu'
    assert result.shape == (1, 512, 1024)
    torch.testing.assert_close(result[:, :10], value[:, :10].bfloat16(), rtol=0, atol=0)
    assert torch.count_nonzero(result[:, 10:]) == 0


@pytest.mark.parametrize('value', [torch.zeros(1, 512, 1024),
                                  torch.full((1, 512, 1024), float('nan')),
                                  torch.ones(1, 512, 768)])
def test_t5_rejects_invalid_encoder_results(value):
    model = lambda **kwargs: SimpleNamespace(last_hidden_state=value)
    with pytest.raises(ValueError):
        encode_commands(Tokenizer(), model, ['pick up the blue block on the table'], 'cpu')
