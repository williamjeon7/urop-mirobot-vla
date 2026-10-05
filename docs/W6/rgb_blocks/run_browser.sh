#!/usr/bin/env bash
# Start the localhost viewer on OASYS; no Windows launcher or saved media.
set -eo pipefail

rgb_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
rgb_conda_hook="~/miniforge3/etc/profile.d/conda.sh"
if [[ ! -r "$rgb_conda_hook" ]]; then
    printf 'Conda setup not found: %s\n' "$rgb_conda_hook" >&2
    exit 1
fi

source "$rgb_conda_hook"
conda activate libero
exec "$CONDA_PREFIX/bin/python" -B "$rgb_script_dir/browser_viewer.py" "$@"
