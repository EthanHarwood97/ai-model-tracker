$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
python -m model_tracker.cli serve
