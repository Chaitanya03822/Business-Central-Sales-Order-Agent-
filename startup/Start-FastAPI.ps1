
$ErrorActionPreference = "Stop"
Set-Location "C:\AI-BC-Agent"

$python = "C:\AI-BC-Agent\venv\Scripts\python.exe"
$log = "C:\AI-BC-Agent\startup\fastapi-startup.log"

if (-not (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue)) {
    & $python -m uvicorn main:app --host 0.0.0.0 --port 8001 *>> $log
}
