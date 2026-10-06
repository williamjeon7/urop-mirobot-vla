param(
    [string]$PythonPath,
    [string]$ConfigDirectory,
    [switch]$Setup,
    [switch]$Browser,
    [ValidateSet('scene', 'red', 'green', 'blue')]
    [string]$Task = 'scene',
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
    if ($Browser -and $Headless) {
        throw 'Use -Browser for the browser viewer or -Headless for verification.'
    }
    # Only machine-specific paths are saved; runtime environment stays in this process.
    $settingsFile = Join-Path $PSScriptRoot 'windows.local.json'
    if (Test-Path -LiteralPath $settingsFile -PathType Leaf) {
        $settings = Get-Content -LiteralPath $settingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $PythonPath) { $PythonPath = $settings.PythonPath }
        if (-not $ConfigDirectory) { $ConfigDirectory = $settings.ConfigDirectory }
    } elseif (-not $Setup) {
        throw 'Run run_local.cmd -Setup once on this laptop before launching the viewer.'
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
        throw 'W5 libero Python not found. Complete the W5 setup, then run run_local.cmd -Setup -PythonPath "C:\path\to\libero\python.exe".'
    }
    $PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
    $liberoEnvironment = Split-Path -Parent $PythonPath
    $env:PATH = "$liberoEnvironment;$liberoEnvironment\Library\bin;$liberoEnvironment\Scripts;$env:PATH"
    $env:MUJOCO_GL = 'wgl'
    $env:NUMBA_DISABLE_JIT = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'

    # Prevent LIBERO's first-import setup prompt and automatic config creation.
    if (-not $ConfigDirectory) {
        $ConfigDirectory = $env:LIBERO_CONFIG_PATH
    }
    if (-not $ConfigDirectory) {
        $ConfigDirectory = Join-Path $env:USERPROFILE '.libero'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ConfigDirectory 'config.yaml') -PathType Leaf)) {
        throw 'Existing LIBERO config.yaml not found. Complete the working W5 setup first.'
    }
    $ConfigDirectory = (Resolve-Path -LiteralPath $ConfigDirectory).Path
    $env:LIBERO_CONFIG_PATH = $ConfigDirectory

    # Inspect W5's WGL/DLL fixes without modifying installed packages.
    $compatibility = Join-Path $PSScriptRoot '..\..\W5\custom_task_validation\configure_libero_windows.py'
    & $PythonPath $compatibility
    if ($LASTEXITCODE -ne 0) {
        throw 'Windows compatibility check failed. Follow W5 NewTaskBDDL Windows setup before retrying.'
    }

    if ($Setup) {
        @{
            PythonPath = $PythonPath
            ConfigDirectory = $ConfigDirectory
        } | ConvertTo-Json | Set-Content -LiteralPath $settingsFile -Encoding UTF8
        Write-Host "Laptop setup saved: $settingsFile"
        Write-Host 'From a new terminal, run run_local.cmd to open the viewer.'
        exit 0
    }

    $viewer = Join-Path $PSScriptRoot 'test_rgb_blocks.py'
    if ($Browser) { $viewer = Join-Path $PSScriptRoot 'browser_viewer.py' }
    $viewerArgs = @('-B', $viewer, '--task', $Task, '--size', "$Size", '--seed', "$Seed")
    if (-not $Browser) {
        $viewerArgs += @('--steps', "$Steps")
        if ($Headless) { $viewerArgs += '--headless' }
    }
    Write-Host "Python: $PythonPath"
    if ($Browser) {
        Write-Host 'Local browser viewer: http://localhost:8766 | Ctrl+C to finish.'
    } elseif (-not $Headless) {
        Write-Host 'Local OpenCV viewer: q / Q / Esc or close the window to finish. No files are saved.'
    }
    & $PythonPath @viewerArgs
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
