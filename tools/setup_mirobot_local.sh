#!/usr/bin/env bash
# Keep local USB dependencies separate from the trained Cosmos environment.
set -euo pipefail
TASK_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_REPO"
TASK_PYTHON="${MIROBOT_SETUP_PYTHON:-$TASK_REPO/cosmos-policy/.venv/bin/python}"
TASK_VENV="$TASK_REPO/urop"

if [[ ! -x "$TASK_PYTHON" ]]; then
    TASK_PYTHON="$(command -v python3.10 || true)"
fi
if [[ -z "$TASK_PYTHON" ]]; then
    echo 'Python 3.10이 필요합니다. MIROBOT_SETUP_PYTHON으로 실행 파일을 지정하세요.' >&2
    exit 1
fi
"$TASK_PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 10), "Python 3.10 required"'

if [[ ! -x "$TASK_VENV/bin/python" ]]; then
    if command -v uv >/dev/null 2>&1; then
        uv venv --python "$TASK_PYTHON" "$TASK_VENV"
    else
        "$TASK_PYTHON" -m venv "$TASK_VENV"
    fi
fi
"$TASK_VENV/bin/python" -c 'import sys; assert sys.version_info[:2] == (3, 10), "urop must use Python 3.10"'
if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$TASK_VENV/bin/python" -r requirements/policy_robot.txt
    uv pip install --python "$TASK_VENV/bin/python" --no-deps -e .
else
    "$TASK_VENV/bin/python" -m pip install -r requirements/policy_robot.txt
    "$TASK_VENV/bin/python" -m pip install --no-deps -e .
fi
echo '설치 완료. 장치 확인: bash tools/run_mirobot_local.sh --devices'
