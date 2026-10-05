param(
    [string]$PythonPath,
    [switch]$Headless,
    [int]$Steps = 60,
    [int]$Size = 512,
    [int]$Seed = 0
)

# Run on the Windows PC, not in the VS Code Remote-SSH terminal.
$ErrorActionPreference = 'Stop'
try {
    if ($env:OS -ne 'Windows_NT') {
        throw 'Run this launcher on your local Windows PC, not on OASYS.'
    }
    if (-not $PythonPath) {
        # Reuse the working W5 environment; never install or select system Python.
        $candidates = @()
        if ($env:CONDA_DEFAULT_ENV -eq 'libero' -and $env:CONDA_PREFIX) {
            $candidates += Join-Path $env:CONDA_PREFIX 'python.exe'
        }
        foreach ($installation in @('anaconda3', 'miniforge3', 'miniconda3')) {
            $candidates += Join-Path $env:USERPROFILE "$installation\envs\libero\python.exe"
        }
        $PythonPath = $candidates | Where-Object {
            Test-Path -LiteralPath $_ -PathType Leaf
        } | Select-Object -First 1
    }
    if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw 'W5 libero Python not found. Use run_local.ps1 -PythonPath "C:\path\to\libero\python.exe" or complete the W5 setup.'
    }
    $PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
    $liberoEnvironment = Split-Path -Parent $PythonPath
    $env:PATH = "$liberoEnvironment;$liberoEnvironment\Library\bin;$liberoEnvironment\Scripts;$env:PATH"
    $env:MUJOCO_GL = 'wgl'
    $env:NUMBA_DISABLE_JIT = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'

    # Prevent LIBERO's first-import setup prompt and automatic config creation.
    $configDirectory = $env:LIBERO_CONFIG_PATH
    if (-not $configDirectory) {
        $configDirectory = Join-Path $env:USERPROFILE '.libero'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $configDirectory 'config.yaml') -PathType Leaf)) {
        throw 'Existing LIBERO config.yaml not found. Complete the working W5 setup first.'
    }
    $env:LIBERO_CONFIG_PATH = $configDirectory

    # Inspect W5's WGL/DLL fixes without modifying installed packages.
    $compatibility = Join-Path $PSScriptRoot '..\..\W5\custom_task_validation\configure_libero_windows.py'
    & $PythonPath $compatibility
    if ($LASTEXITCODE -ne 0) {
        throw 'Windows compatibility check failed. Follow W5 NewTaskBDDL Windows setup before retrying.'
    }

    $viewer = Join-Path $PSScriptRoot 'test_rgb_blocks.py'
    $viewerArgs = @($viewer, '--steps', "$Steps", '--size', "$Size", '--seed', "$Seed")
    if ($Headless) { $viewerArgs += '--headless' }
    Write-Host "Python: $PythonPath"
    Write-Host 'Local OpenCV viewer: q / Q / Esc or close the window to finish. No files are saved.'
    & $PythonPath @viewerArgs
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
