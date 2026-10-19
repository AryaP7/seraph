param(
    [string]$Store = "$PSScriptRoot/prototype_runs/seraph.sqlite",
    [string]$NewsStore = "$PSScriptRoot/prototype_runs/news-intelligence-pilot.sqlite",
    [int]$Port = 8512,
    [switch]$NoNewsWorker
)
$ErrorActionPreference = 'Stop'
$env:SERAPH_PROTOTYPE_STORE = $Store
$env:SERAPH_NEWS_STORE = $NewsStore
$Python = "$PSScriptRoot/.venv/Scripts/python.exe"
$Worker = $null
try {
    if (-not $NoNewsWorker) {
        # Registration runs on EVERY launch, not only when the store is
        # missing. It is idempotent, and gating it on a missing file meant an
        # existing database never received a newly added source: the catalogue
        # in run_news.py could gain a feed that silently never got fetched.
        # The worker reconciles the reviewed catalogue on every launch.
        # Cached screens are served immediately while acquisition runs;
        # explicit --register --reprobe remains available for source audits.

        # --catch-up polls every source once before entering the loop. Without
        # it a worker restarted shortly after a poll waits out the remaining
        # interval while the server shows hours-old data under a healthy
        # worker.
        # Supervised, not bare. A bare worker that dies stays dead and the
        # console shows a stopped heartbeat forever; the supervisor restarts
        # it with backoff and, after a bounded number of failures, records
        # `failed` rather than looping quietly.
        $Worker = Start-Process -FilePath $Python -ArgumentList @(
            "`"$PSScriptRoot/scripts/news_supervisor.py`"", '--store', "`"$NewsStore`"",
            '--interval', '30', '--max-restarts', '5'
        ) -WorkingDirectory $PSScriptRoot -PassThru -WindowStyle Hidden `
          -RedirectStandardOutput "$PSScriptRoot/prototype_runs/news-worker.log" `
          -RedirectStandardError "$PSScriptRoot/prototype_runs/news-worker-errors.log"
    }
    & $Python -m streamlit run "$PSScriptRoot/seraph/dashboard/prototype_app.py" --server.address 127.0.0.1 --server.port $Port --server.headless true
} finally {
    if ($Worker -and -not $Worker.HasExited) {
        & taskkill /PID $Worker.Id /T /F | Out-Null
    }
}
