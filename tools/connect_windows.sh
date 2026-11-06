#!/usr/bin/env bash
# Prepare one-time Windows installation/key pairing from the OASYS terminal.
set -euo pipefail
TASK_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_REPO"
if [[ ! -x "$TASK_REPO/urop/bin/python" ]]; then
    bash "$TASK_REPO/tools/setup_mirobot_local.sh"
fi
exec "$TASK_REPO/urop/bin/python" -m tools.pair_windows "$@"
