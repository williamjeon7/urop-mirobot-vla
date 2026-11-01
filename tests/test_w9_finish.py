import json
from pathlib import Path

import pytest

from docs.W9.d405 import finish_server


@pytest.mark.parametrize('pretrained_loaded', [True, False, None])
def test_finish_requires_pretrained_smoke_and_preserves_checkpoint_symlink(tmp_path, monkeypatch,
                                                                          pretrained_loaded):
    data = tmp_path/'data'
    data.mkdir()
    (data/'t5_embeddings.pkl').write_bytes(b'test fixture; actual embedding check is mocked')
    (data/'loader_validation.json').write_text(json.dumps(dict(training_ready=True)))
    (data/'training_smoke.json').write_text(json.dumps(dict(status='passed',
        pretrained_checkpoint_loaded=pretrained_loaded)))
    blob = tmp_path/'extensionless_blob'
    blob.write_bytes(b'test checkpoint')
    checkpoint = tmp_path/'snapshot.pt'
    checkpoint.symlink_to(blob)
    commands = []
    monkeypatch.setattr(finish_server, 'run', lambda command, *args: commands.append(command))
    monkeypatch.setattr(finish_server, 'check', lambda *args: dict(episodes=1,
        instructions=['pick up the blue block on the table']))
    monkeypatch.setattr(finish_server, 'check_embeddings', lambda *args: None)
    monkeypatch.setattr('sys.argv', ['finish_server', '--episodes', str(tmp_path/'episode'),
        '--data-dir', str(data), '--target', 'blue', '--real-success', '--gpus', '4', '--smoke',
        '--statistics', str(tmp_path/'stats.json'), '--checkpoint', str(checkpoint)])
    if pretrained_loaded is True:
        finish_server.main()
    else:
        with pytest.raises(ValueError, match='training validation'):
            finish_server.main()
    training_commands = [command for command in commands if 'docs.W9.d405.train' in command]
    assert len(training_commands) == 2
    for command in training_commands:
        chosen = command[command.index('--checkpoint')+1]
        assert Path(chosen) == checkpoint
        assert Path(chosen).suffix == '.pt'
    result = json.loads((data/'ready.json').read_text())
    assert result['status'] == ('ready' if pretrained_loaded is True else 'failed')
