param(
    [string]$PythonPath,
    [string]$ConfigDirectory,
    [switch]$Setup,
    # Kept for commands written before the browser became the default.
    [switch]$Browser,
    [switch]$OpenCV,
    [ValidateSet('scene', 'red', 'green', 'blue')]
    [string]$Task = 'scene',
    [switch]$Headless,
    [int]$Steps = 60,
    [int]$Size = 512,
    [int]$Seed = 0,
    [ValidateRange(1, 65535)]
    [int]$Port = 8766,
    [ValidateSet('view', 'pickup', 'reach')]
    [string]$Mode = 'view',
    [switch]$Pickup,
    [ValidateSet('none', 'adjacent', 'sandwich')]
    [string]$Scenario = 'none',
    [double]$Fps = 20.0,
    [switch]$Stop
)

# Run on the Windows PC, not in the VS Code Remote-SSH terminal.
$ErrorActionPreference = 'Stop'
try {
    if ($env:OS -ne 'Windows_NT') {
        throw 'Run this launcher on your local Windows PC, not on OASYS.'
    }
    if (($Browser -and ($OpenCV -or $Headless)) -or ($OpenCV -and $Headless)) {
        throw 'Choose the default browser viewer, -OpenCV, or -Headless separately.'
    }
    if ($Stop -and ($Setup -or $OpenCV -or $Headless)) {
        throw 'Use -Stop only to stop the browser viewer, optionally with -Port.'
    }
    $useBrowser = -not ($OpenCV -or $Headless)
    if (-not $Setup -and -not $useBrowser) {
        foreach ($option in @('Port', 'Mode', 'Pickup', 'Scenario', 'Fps', 'Stop')) {
            if ($PSBoundParameters.ContainsKey($option)) {
                throw "-$option is available only in the browser viewer."
            }
        }
    }
    if (-not $Setup -and $useBrowser -and $PSBoundParameters.ContainsKey('Steps')) {
        throw '-Steps is for -OpenCV or -Headless. Browser placement episodes use 60 steps.'
    }
    if ($Pickup -and $PSBoundParameters.ContainsKey('Mode') -and $Mode -ne 'pickup') {
        throw '-Pickup conflicts with -Mode. Use -Mode pickup or -Pickup.'
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
    if (-not $PythonPath) {
        throw 'No W5 libero Python was detected. Locate the installed libero environment and pass its existing python.exe with -Setup -PythonPath.'
    }
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw "Python executable not found: $PythonPath. Use your actual installed libero Python path. If you copied a README example, retry run_local.cmd -Setup without path options."
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
    $configFile = [System.IO.Path]::Combine($ConfigDirectory, 'config.yaml')
    if (-not (Test-Path -LiteralPath $configFile -PathType Leaf)) {
        throw "Existing LIBERO config.yaml not found: $configFile. Use the actual W5 configuration folder with -ConfigDirectory."
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
        Write-Host 'From a new terminal, run run_local.cmd, then open http://localhost:8766.'
        exit 0
    }

    if ($useBrowser) {
        $viewer = Join-Path $PSScriptRoot 'browser_viewer.py'
        $viewerArgs = @('-B', $viewer, '--port', "$Port")
        if ($Stop) {
            $viewerArgs += '--stop'
        } else {
            if ($Pickup) { $Mode = 'pickup' }
            $viewerArgs += @('--task', $Task, '--mode', $Mode, '--scenario', $Scenario,
                '--size', "$Size", '--seed', "$Seed", '--fps', $Fps.ToString('R', [System.Globalization.CultureInfo]::InvariantCulture))
        }
    } else {
        $viewer = Join-Path $PSScriptRoot 'test_rgb_blocks.py'
        $viewerArgs = @('-B', $viewer, '--task', $Task, '--size', "$Size", '--seed', "$Seed", '--steps', "$Steps")
        if ($Headless) { $viewerArgs += '--headless' }
    }
    Write-Host "Python: $PythonPath"
    if ($Stop) {
        Write-Host "Stopping local browser viewer: http://localhost:$Port"
    } elseif ($useBrowser) {
        Write-Host "Local browser viewer: http://localhost:$Port | Ctrl+C to finish."
    } elseif (-not $Headless) {
        Write-Host 'Local OpenCV viewer: q / Q / Esc or close the window to finish. No files are saved.'
    }
    & $PythonPath @viewerArgs
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
