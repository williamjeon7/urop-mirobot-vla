#!/usr/bin/env bash
# GPU server entry point. Defaults to a command preview; --execute sends motion.
set -euo pipefail
TASK_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_REPO"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-${MIROBOT_GPU:-2}}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export MUJOCO_GL="${MUJOCO_GL:-egl}"
exec "$TASK_REPO/cosmos-policy/.venv/bin/python" -m server.run_policy "$@"
