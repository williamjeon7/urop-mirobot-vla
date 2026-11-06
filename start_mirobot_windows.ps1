# Keep USB on Windows; control inference from the existing VS Code OASYS Bash.
param(
    [string]$SerialPort = "",
    [string]$ServerAddress = "<SERVER_IP>",
    [int]$SshPort = <SSH_PORT>,
    [string]$ServerUser = "<USER>",
    [switch]$Stop
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSCommandPath
Set-Location $repo
$runtimeDirectory = Join-Path $env:LOCALAPPDATA "mirobot-policy"
$pidFile = Join-Path $runtimeDirectory "bridge-owner.pid"
$stopFile = Join-Path $runtimeDirectory "bridge-stop.request"

if ($Stop) {
    if (!(Test-Path $pidFile)) {
        Write-Host "Windows USB bridge is not running."
        exit 0
    }
    $ownerPid = 0
    $parsedPid = [int]::TryParse((Get-Content -LiteralPath $pidFile -Raw), [ref]$ownerPid)
    if (!$parsedPid -or $null -eq (Get-Process -Id $ownerPid -ErrorAction SilentlyContinue)) {
        Remove-Item -LiteralPath $pidFile, $stopFile -Force -ErrorAction SilentlyContinue
        Write-Host "Removed stale bridge state."
        exit 0
    }
    [System.IO.File]::WriteAllText($stopFile, "stop")
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (!(Test-Path $pidFile)) {
            Write-Host "Windows USB bridge stopped."
            exit 0
        }
        Start-Sleep -Seconds 1
    }
    throw "Bridge did not stop within 30 seconds."
}

$null = New-Item -ItemType Directory -Path $runtimeDirectory -Force
if (Test-Path $pidFile) {
    $ownerPid = 0
    $parsedPid = [int]::TryParse((Get-Content -LiteralPath $pidFile -Raw), [ref]$ownerPid)
    if ($parsedPid -and $null -ne (Get-Process -Id $ownerPid -ErrorAction SilentlyContinue)) {
        throw "Windows USB bridge is already running. Stop it with start_mirobot_windows.cmd -Stop."
    }
    Remove-Item -LiteralPath $pidFile, $stopFile -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue
[System.IO.File]::WriteAllText($pidFile, [string]$PID)
$bridgeProcess = $null
$tunnelProcess = $null
try {
    $key = Join-Path $HOME ".ssh\mirobot_oasys"
    $sshOptions = @("-p", "$SshPort", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=8")
    $knownHosts = Join-Path $HOME ".ssh\mirobot_oasys_known_hosts"
    if (Test-Path $knownHosts) {
        $sshOptions = @("-p", "$SshPort", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=$knownHosts", "-o", "ConnectTimeout=8")
    }
    if (Test-Path $key) { $sshOptions += @("-o", "IdentitiesOnly=yes", "-i", $key) }
    $target = "${ServerUser}@${ServerAddress}"
    & ssh.exe @sshOptions $target true
    if ($LASTEXITCODE -ne 0) {
        if (!(Test-Path $key)) {
            New-Item -ItemType Directory -Force (Split-Path -Parent $key) | Out-Null
            # ProcessStartInfo preserves the empty passphrase on Windows PowerShell 5.
            $start = New-Object System.Diagnostics.ProcessStartInfo
            $start.FileName = "ssh-keygen.exe"
            $start.Arguments = '-t ed25519 -N "" -f "{0}"' -f $key
            $start.UseShellExecute = $false
            $generate = [System.Diagnostics.Process]::Start($start)
            $generate.WaitForExit()
            if ($generate.ExitCode -ne 0) { throw "SSH key generation failed." }
        }
        Write-Host "KEY REGISTRATION REQUIRED: paste ONLY the public key below into the chat:"
        Get-Content "$key.pub"
        throw "Register this public key on OASYS, then run this launcher again. No password login is attempted."
    }
    $python = Join-Path $repo "urop\Scripts\python.exe"
    if (!(Test-Path $python)) {
        & py.exe -3.10 -m venv urop
        if ($LASTEXITCODE -ne 0) { throw "Python 3.10 is required on this Windows PC." }
    }
    & $python -m pip install -r requirements/policy_robot.txt
    if ($LASTEXITCODE -ne 0) { throw "Robot dependency installation failed." }
    & $python -m pip install --no-deps -e .
    if ($LASTEXITCODE -ne 0) { throw "Project installation failed." }
    if (!$SerialPort) {
        $ports = & $python -c "import json; from serial.tools import list_ports; print(json.dumps([p.device for p in list_ports.comports() if p.vid is not None]))"
        if ($LASTEXITCODE -ne 0) { throw "Serial port lookup failed." }
        $candidates = @(ConvertFrom-Json $ports)
        if ($candidates.Count -ne 1) { throw "Specify the robot port: start_mirobot_windows.cmd -SerialPort COM3. Found: $ports" }
        $SerialPort = $candidates[0]
    }
    & $python -m docs.W9.d405.devices --check --robot-port $SerialPort
    if ($LASTEXITCODE -ne 0) { throw "Connect Mirobot and D405 to this Windows PC." }
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 8891)
    try { $probe.Start() } finally { $probe.Stop() }
    $videoDirectory = Join-Path $repo "policy_recordings"
    $arguments = '-m robot.policy_bridge --serial-port "{0}" --execute --video-dir "{1}"' -f $SerialPort, $videoDirectory
    $bridgeProcess = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $repo -NoNewWindow -PassThru
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($bridgeProcess.HasExited) { throw "USB bridge exited; check its device error above." }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8891/health" -TimeoutSec 1
            if ($health.ok) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (!$ready) { throw "USB bridge did not become ready." }
    Write-Host "Bridge stays active until stopped with start_mirobot_windows.cmd -Stop."
    Write-Host "In the existing OASYS VS Code Bash run:"
    Write-Host "bash tools/run_mirobot_local.sh --devices"
    Write-Host "bash tools/run_mirobot_local.sh --color red --max-steps 4"
    $sshOptions += @("-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3")
    $tunnelOptions = @($sshOptions) + @("-N", "-R", "127.0.0.1:8891:127.0.0.1:8891", $target)
    $tunnelArguments = ($tunnelOptions | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' }) -join " "
    while (!(Test-Path $stopFile)) {
        if ($bridgeProcess.HasExited) { throw "USB bridge exited; check its device error above." }
        $tunnelProcess = Start-Process -FilePath "ssh.exe" -ArgumentList $tunnelArguments -WorkingDirectory $repo -NoNewWindow -PassThru
        Write-Host "SSH tunnel active. It will reconnect if the network drops."
        while (!$tunnelProcess.HasExited) {
            if ($bridgeProcess.HasExited) { throw "USB bridge exited; check its device error above." }
            if (Test-Path $stopFile) {
                Stop-Process -Id $tunnelProcess.Id -ErrorAction SilentlyContinue
                break
            }
            Start-Sleep -Seconds 1
        }
        $tunnelProcess.WaitForExit()
        $tunnelProcess = $null
        if (!(Test-Path $stopFile)) {
            Write-Warning "SSH tunnel ended; the USB bridge remains active and the tunnel will retry."
            for ($retry = 0; $retry -lt 5 -and !(Test-Path $stopFile); $retry++) {
                Start-Sleep -Seconds 1
            }
        }
    }
} catch {
    Write-Host $_ -ForegroundColor Red
    exit 1
} finally {
    if ($null -ne $tunnelProcess -and !$tunnelProcess.HasExited) {
        Stop-Process -Id $tunnelProcess.Id -ErrorAction SilentlyContinue
    }
    if ($null -ne $bridgeProcess -and !$bridgeProcess.HasExited) {
        Stop-Process -Id $bridgeProcess.Id -ErrorAction SilentlyContinue
    }
    if ((Test-Path $pidFile) -and (Get-Content -LiteralPath $pidFile -Raw) -eq [string]$PID) {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue
}
