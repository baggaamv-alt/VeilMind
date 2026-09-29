# Windows PowerShell: .\run.ps1   (same as double-clicking "Start Veilmind (Windows).bat")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (Get-Command py -ErrorAction SilentlyContinue) { py -3 start.py @args } else { python start.py @args }
