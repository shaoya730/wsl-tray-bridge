param([ValidatePattern('^[A-Za-z0-9_.-]+$')][string]$Distro = 'Ubuntu')
$ErrorActionPreference = 'Stop'
& wsl.exe -d $Distro --exec systemctl --user disable --now wsl-tray-bridge.service
if ($LASTEXITCODE -ne 0) { throw 'Could not stop and disable the Linux bridge' }
$taskInstall = Join-Path $env:LOCALAPPDATA 'Programs\WSLTrayBridge'
$taskLinks = @(
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'WSL Apps\WSL Tray Bridge.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'WSL Tray Bridge.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Startup')) 'WSL Tray Bridge.lnk')
)
foreach ($taskLink in $taskLinks) {
    if (Test-Path -LiteralPath $taskLink) { Remove-Item -LiteralPath $taskLink }
}
foreach ($taskName in @('WSLTrayBridge.exe','config.json','README.md','WSL Tray Bridge.lnk')) {
    $taskFile = Join-Path $taskInstall $taskName
    if (Test-Path -LiteralPath $taskFile) { Remove-Item -LiteralPath $taskFile }
}
Write-Output 'Bridge disabled and Windows executable removed. Logs, Linux helpers and shared dependencies were preserved.'
