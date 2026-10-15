$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -eq 'Core') {
    & "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $PSCommandPath
    if ($LASTEXITCODE -ne 0) { throw 'Shutdown tests failed' }
    return
}
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskBuild = Join-Path $taskRoot 'build'
New-Item -ItemType Directory -Force -Path $taskBuild | Out-Null
$taskOutput = Join-Path $taskBuild 'ShutdownTests.exe'
if (Test-Path -LiteralPath $taskOutput) { Remove-Item -LiteralPath $taskOutput }
$taskCompiler = New-Object System.CodeDom.Compiler.CompilerParameters
$taskCompiler.GenerateExecutable = $true
$taskCompiler.OutputAssembly = $taskOutput
$taskCompiler.CompilerOptions = '/target:exe /main:ShutdownTests'
$taskCompiler.ReferencedAssemblies.AddRange(@('System.dll','System.Core.dll','System.Windows.Forms.dll','System.Drawing.dll','System.Web.Extensions.dll'))
Add-Type -Path @((Join-Path $taskRoot 'windows\TrayBridge.cs'), (Join-Path $PSScriptRoot 'ShutdownTests.cs')) -CompilerParameters $taskCompiler
& $taskOutput
if ($LASTEXITCODE -ne 0) { throw 'Shutdown tests failed' }
