#!/usr/bin/env bash
# OASYS auxiliary CPU-check environment. Hardware capture runs on the Windows laptop.
# Never opens the robot serial port.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$repo_dir"
if ! command -v uv >/dev/null 2>&1; then
    echo 'uv is required (already installed on OASYS). Add uv to PATH and retry.' >&2
    exit 1
fi
uv venv --no-project --seed --python /usr/bin/python3 --allow-existing docs/W9/.venv
docs/W9/.venv/bin/python -m pip install -r docs/W9/d405/requirements.txt
docs/W9/.venv/bin/python -m pip check
docs/W9/.venv/bin/python -m pip freeze > docs/W9/installed-packages.local.txt
docs/W9/.venv/bin/python -m docs.W9.d405.capture --list
echo 'W9 ready. No robot commands sent. See docs/W9/COLORCHECKER_MINI.md.'
