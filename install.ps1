param(
    [ValidatePattern('^[A-Za-z0-9_.-]+$')][string]$Distro = 'Ubuntu',
    [switch]$NoLegacy
)
$ErrorActionPreference = 'Stop'
$taskExe = Join-Path $PSScriptRoot 'build\WSLTrayBridge.exe'
if (-not (Test-Path -LiteralPath $taskExe)) { & (Join-Path $PSScriptRoot 'build.ps1') }
if (-not (Test-Path -LiteralPath $taskExe)) { throw 'Build did not produce an executable' }

# Stop an existing service before replacing a running executable.
$taskLinuxHome = (& wsl.exe -d $Distro --exec printenv HOME | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $taskLinuxHome.StartsWith('/')) { throw 'Cannot determine Linux home directory' }
$taskLinuxUnit = '\\wsl.localhost\' + $Distro + ($taskLinuxHome.Replace('/','\')) + '\.config\systemd\user\wsl-tray-bridge.service'
if (Test-Path -LiteralPath $taskLinuxUnit) {
    & wsl.exe -d $Distro --exec systemctl --user stop wsl-tray-bridge.service
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop existing Linux bridge' }
}
$taskInstall = Join-Path $env:LOCALAPPDATA 'Programs\WSLTrayBridge'
New-Item -ItemType Directory -Force -Path $taskInstall | Out-Null
Copy-Item -LiteralPath $taskExe -Destination (Join-Path $taskInstall 'WSLTrayBridge.exe') -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README.md') -Destination (Join-Path $taskInstall 'README.md') -Force
@{distro=$Distro} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskInstall 'config.json') -Encoding UTF8

# All dependency packages come from the configured Ubuntu repositories.
& wsl.exe -d $Distro -u root --exec apt-get update
if ($LASTEXITCODE -ne 0) { throw 'Ubuntu package index update failed' }
$taskDependencies = @('python3-dbus','python3-gi','gir1.2-gtk-3.0')
if (-not $NoLegacy) {
    $taskDependencies += @('libkf5windowsystem5','libxcb-composite0','libxcb-damage0','libxcb-image0','libxcb-util1','libxcb-shape0','libxtst6','libqt5dbus5t64','libqt5widgets5t64','libqt5x11extras5')
}
& wsl.exe -d $Distro -u root --exec apt-get install -y --no-install-recommends @taskDependencies
if ($LASTEXITCODE -ne 0) { throw 'Linux dependency installation failed' }

$taskLinuxExe = (& wsl.exe -d $Distro --exec wslpath -u (Join-Path $taskInstall 'WSLTrayBridge.exe') | Out-String).Trim()
$taskLinuxSetup = (& wsl.exe -d $Distro --exec wslpath -u (Join-Path $PSScriptRoot 'scripts\configure_linux.py') | Out-String).Trim()
$taskSetupArguments = @('--windows-exe',$taskLinuxExe)
if ($NoLegacy) { $taskSetupArguments += '--no-legacy' }
& wsl.exe -d $Distro --exec python3 $taskLinuxSetup @taskSetupArguments
if ($LASTEXITCODE -ne 0) { throw 'Linux service installation failed' }

$taskPrograms = Join-Path ([Environment]::GetFolderPath('Programs')) 'WSL Apps'
New-Item -ItemType Directory -Force -Path $taskPrograms | Out-Null
$taskTempLink = Join-Path $taskInstall 'WSL Tray Bridge.lnk'
$taskShell = New-Object -ComObject WScript.Shell
$taskShortcut = $taskShell.CreateShortcut($taskTempLink)
$taskWslg = Join-Path $env:ProgramFiles 'WSL\wslg.exe'
if (-not (Test-Path -LiteralPath $taskWslg)) { throw 'Cannot locate WSLg; Linux service was installed, but no shortcut was created' }
$taskShortcut.TargetPath = $taskWslg
$taskShortcut.Arguments = '-d ' + $Distro + ' -- /usr/bin/systemctl --user start wsl-tray-bridge.service'
$taskShortcut.WorkingDirectory = $taskInstall
$taskShortcut.Description = 'Start Linux-managed tray integration'
$taskShortcut.Save()
foreach ($taskFolder in @($taskPrograms, [Environment]::GetFolderPath('Desktop'))) {
    Copy-Item -LiteralPath $taskTempLink -Destination (Join-Path $taskFolder 'WSL Tray Bridge.lnk') -Force
}
$taskStartupLink = Join-Path ([Environment]::GetFolderPath('Startup')) 'WSL Tray Bridge.lnk'
if (Test-Path -LiteralPath $taskStartupLink) { Remove-Item -LiteralPath $taskStartupLink }
Write-Output 'Installed. The Linux user service owns startup and shutdown; no Windows login watcher is installed.'
