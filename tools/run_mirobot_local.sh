#!/usr/bin/env bash
# Run OASYS inference with directly connected USB or the Windows USB bridge.
set -euo pipefail
TASK_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_REPO"
if [[ ! -x "$TASK_REPO/urop/bin/python" ]]; then
    echo '먼저 bash tools/setup_mirobot_local.sh 를 실행하세요.' >&2
    exit 1
fi
exec "$TASK_REPO/urop/bin/python" -m tools.run_mirobot_local "$@"
