#!/usr/bin/env bash
# Start the Windows USB installer/bridge from a local Git Bash or WSL terminal.
set -euo pipefail
TASK_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v powershell.exe >/dev/null 2>&1; then
    echo '이 명령은 Windows 로컬 Bash에서 실행해야 합니다.' >&2
    echo '현재 VS Code에서 Ctrl+Shift+P → Terminal: Create New Integrated Terminal (Local)' >&2
    exit 1
fi
if command -v cygpath >/dev/null 2>&1; then
    TASK_LAUNCHER="$(cygpath -w "$TASK_REPO/start_mirobot_windows.ps1")"
elif command -v wslpath >/dev/null 2>&1; then
    TASK_LAUNCHER="$(wslpath -w "$TASK_REPO/start_mirobot_windows.ps1")"
else
    echo 'Windows Git Bash 또는 Windows와 연동된 WSL 터미널이 필요합니다.' >&2
    exit 1
fi
MSYS2_ARG_CONV_EXCL='*' exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$TASK_LAUNCHER" "$@"
