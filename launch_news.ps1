param(
    [string]$Store = "$PSScriptRoot/prototype_runs/news-intelligence-pilot.sqlite"
)
$ErrorActionPreference = 'Stop'
$Python = "$PSScriptRoot/.venv/Scripts/python.exe"
& $Python "$PSScriptRoot/scripts/run_news.py" --store $Store --register --reprobe
if ($LASTEXITCODE -ne 0) { throw 'News source registration failed' }
& $Python "$PSScriptRoot/scripts/news_supervisor.py" --store $Store --interval 30 --max-restarts 5
