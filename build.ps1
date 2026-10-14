$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -eq 'Core') {
    & "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $PSCommandPath
    if ($LASTEXITCODE -ne 0) { throw 'Windows PowerShell build failed' }
    return
}
$taskBuild = Join-Path $PSScriptRoot 'build'
New-Item -ItemType Directory -Force -Path $taskBuild | Out-Null
$taskOutput = Join-Path $taskBuild 'WSLTrayBridge.exe'
if (Test-Path -LiteralPath $taskOutput) { Remove-Item -LiteralPath $taskOutput }
Add-Type -Path (Join-Path $PSScriptRoot 'windows\TrayBridge.cs') -ReferencedAssemblies @('System.dll','System.Core.dll','System.Windows.Forms.dll','System.Drawing.dll','System.Web.Extensions.dll') -OutputAssembly $taskOutput -OutputType WindowsApplication
Get-Item -LiteralPath $taskOutput | Select-Object FullName,Length
