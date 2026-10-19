<#
    The canonical way to run SERAPH.

        .\launch_prototype.ps1

    Starts the console and exactly one supervised news acquisition worker
    against the same database.

    Two ways in, one outcome. This launcher starts the worker immediately,
    because a server with no browser session attached has not run the app
    script yet and would otherwise fetch nothing until somebody opened the
    page. Every other way of starting the same application --
    `.claude/launch.json`, a bare `streamlit run`, an IDE run button --
    gets its worker from the app itself on the first page view
    (seraph/dashboard/news_service.py). An OS lock, not either of those
    code paths, is what guarantees there is only ever one: whichever moves
    first wins and the other stands aside and says so on screen.

    Shutdown: the worker is told to watch this launcher's process id, so
    Ctrl+C, a closed window and a hard kill all stop it. The `finally`
    below signals only the process this script started.

    -NoNewsWorker runs the console against the store exactly as it is. The
    screen then says nothing is fetching, which is true.
#>
param(
    [string]$Store = "$PSScriptRoot/prototype_runs/seraph.sqlite",
    [string]$NewsStore = "$PSScriptRoot/prototype_runs/news-intelligence-pilot.sqlite",
    [string]$LiveStore = "$PSScriptRoot/prototype_runs/live.sqlite",
    [int]$Port = 8512,
    [switch]$NoNewsWorker
)
$ErrorActionPreference = 'Stop'
$env:SERAPH_PROTOTYPE_STORE = $Store
$env:SERAPH_NEWS_STORE = $NewsStore
$env:SERAPH_LIVE_STORE = $LiveStore
$env:SERAPH_NEWS_WORKER = if ($NoNewsWorker) { '0' } else { '1' }

$Python = "$PSScriptRoot/.venv/Scripts/python.exe"
$Worker = $null
try {
    if (-not $NoNewsWorker) {
        New-Item -ItemType Directory -Force "$PSScriptRoot/prototype_runs" | Out-Null
        # --catch-up polls every source once before entering the loop, after
        # recording collection gaps, so current news arrives promptly and the
        # historical backfill never holds it up.
        $Worker = Start-Process -FilePath $Python -ArgumentList @(
            "`"$PSScriptRoot/scripts/news_supervisor.py`"",
            '--store', "`"$NewsStore`"", '--interval', '30',
            '--max-restarts', '5', '--owner-pid', $PID
        ) -WorkingDirectory $PSScriptRoot -PassThru -WindowStyle Hidden `
          -RedirectStandardOutput "$PSScriptRoot/prototype_runs/news-worker.log" `
          -RedirectStandardError "$PSScriptRoot/prototype_runs/news-worker-errors.log"
        Write-Host "[seraph] news worker supervisor pid $($Worker.Id); log: prototype_runs/news-worker.log"
        # Let it take the single-worker lock before the console probes it,
        # so the console reports "already running" instead of racing it.
        $lock = "$([System.IO.Path]::GetFullPath($NewsStore)).supervisor.lock"
        for ($i = 0; $i -lt 40 -and -not (Test-Path $lock); $i++) { Start-Sleep -Milliseconds 250 }
    } else {
        Write-Host '[seraph] news acquisition disabled for this run (-NoNewsWorker).'
    }
    & $Python -m streamlit run "$PSScriptRoot/seraph/dashboard/prototype_app.py" `
        --server.address 127.0.0.1 --server.port $Port --server.headless true
} finally {
    # Only the process this script started.
    if ($Worker -and -not $Worker.HasExited) {
        & taskkill /PID $Worker.Id /T /F | Out-Null
    }
}
