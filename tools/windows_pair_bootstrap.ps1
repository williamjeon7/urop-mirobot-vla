# Delivered only through a temporary authenticated localhost port forward.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$base = '__BASE__'
function Report-Setup([string]$phase, [string]$detail = '') {
    try {
        $body = @{phase=$phase; error=$detail} | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri "$base/status" -Method Post -ContentType 'application/json' -Body $body | Out-Null
    } catch { }
}
try {
    Report-Setup 'downloading'
    $work = Join-Path ([IO.Path]::GetTempPath()) ('mirobot-pair-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $work | Out-Null
    $archive = Join-Path $work 'mirobot-policy-robot.zip'
    Invoke-WebRequest -UseBasicParsing -Uri "$base/bundle.zip" -OutFile $archive
    if ((Get-FileHash -Algorithm SHA256 $archive).Hash.ToLowerInvariant() -ne '__ARCHIVE_SHA256__') {
        throw 'Bundle verification failed.'
    }
    Expand-Archive -Path $archive -DestinationPath $HOME -Force
    $repo = Join-Path $HOME 'mirobot-policy'
    $sshDirectory = Join-Path $HOME '.ssh'
    New-Item -ItemType Directory -Force $sshDirectory | Out-Null
    $key = Join-Path $sshDirectory 'mirobot_oasys'
    if (!(Test-Path $key)) {
        $start = New-Object System.Diagnostics.ProcessStartInfo
        $start.FileName = 'ssh-keygen.exe'
        $start.Arguments = '-t ed25519 -N "" -f "{0}"' -f $key
        $start.UseShellExecute = $false
        $generate = [Diagnostics.Process]::Start($start)
        $generate.WaitForExit()
        if ($generate.ExitCode -ne 0) { throw 'SSH key generation failed.' }
    }
    $enroll = @{public_key=(Get-Content "$key.pub" -Raw).Trim()} | ConvertTo-Json -Compress
    Invoke-RestMethod -Uri "$base/enroll" -Method Post -ContentType 'application/json' -Body $enroll | Out-Null
    $knownHosts = Join-Path $sshDirectory 'mirobot_oasys_known_hosts'
    '[__SSH_ADDRESS__]:__SSH_PORT__ __SSH_HOST_KEY__' | Set-Content -Encoding ascii $knownHosts
    Report-Setup 'python_setup'
    $venv = Join-Path $repo 'urop\Scripts\python.exe'
    if (!(Test-Path $venv)) {
        $nativePython = $null
        if (Get-Command py.exe -ErrorAction SilentlyContinue) {
            $detect = New-Object System.Diagnostics.ProcessStartInfo
            $detect.FileName = 'py.exe'
            $detect.Arguments = '-3.10 -c "import sys; print(sys.executable)"'
            $detect.UseShellExecute = $false
            $detect.RedirectStandardOutput = $true
            $detect.RedirectStandardError = $true
            $probePython = [Diagnostics.Process]::Start($detect)
            $candidate = $probePython.StandardOutput.ReadToEnd().Trim()
            $null = $probePython.StandardError.ReadToEnd()
            $probePython.WaitForExit()
            if ($probePython.ExitCode -eq 0 -and $candidate) { $nativePython = $candidate }
        }
        if (!$nativePython) {
            $targetPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310'
            $nativePython = Join-Path $targetPython 'python.exe'
            if (!(Test-Path $nativePython)) {
                $installer = Join-Path $work 'python-3.10.11-amd64.exe'
                Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe' -OutFile $installer
                $signature = Get-AuthenticodeSignature $installer
                if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
                    throw 'Python installer signature could not be verified.'
                }
                $arguments = '/quiet InstallAllUsers=0 InstallLauncherAllUsers=0 Include_launcher=0 Include_test=0 PrependPath=0 TargetDir="{0}"' -f $targetPython
                $install = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
                if ($install.ExitCode -ne 0 -and $install.ExitCode -ne 3010) { throw 'Python installation failed.' }
            }
        }
        & $nativePython -m venv (Join-Path $repo 'urop')
        if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
    }
    Report-Setup 'environment_setup'
    & $venv -m pip install -r (Join-Path $repo 'requirements\policy_robot.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Robot dependency installation failed.' }
    & $venv -m pip install --no-deps -e $repo
    if ($LASTEXITCODE -ne 0) { throw 'Project installation failed.' }
    Report-Setup 'bridge_starting'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo 'start_mirobot_windows.ps1') -ServerAddress '__SSH_ADDRESS__' -SshPort __SSH_PORT__ -ServerUser '__SSH_USER__'
    if ($LASTEXITCODE -ne 0) { throw 'Windows bridge setup failed; check the device/SSH error above.' }
} catch {
    Report-Setup 'failed' $_.Exception.Message
    throw
}
