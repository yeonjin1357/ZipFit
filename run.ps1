$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
uv run uvicorn zipfit.main:app --host 127.0.0.1 --port 8765
