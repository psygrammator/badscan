# UTF-8 launcher for Windows PowerShell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
Set-Location -LiteralPath $PSScriptRoot
python -X utf8 -m badscan @args
exit $LASTEXITCODE
