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

    MARKET SIDE (C15). This launcher also brings the market data and
    decisions up to date, so running the application no longer needs a
    second terminal for `run_daily.py` and `run_forecast.py`. That work runs
    in the background through `scripts/run_market_jobs.py`: every step there
    is idempotent, so a relaunch re-runs it harmlessly, and the console's
    startup panel reads the status file it writes.

    Starts one owned market runtime that waits across sessions. Missing/expired
    broker credentials leave it degraded while daily acquisition/news continue.
    -NoLiveRuntime disables the broker runtime explicitly.
    -NativeHawkesConfig enables the native-bar producer with an explicit basket
    and estimation window. Missing history keeps its publication gate closed.

    -NoMarketJobs skips it and leaves the stored vintages and forecasts
    exactly as they are.
#>
param(
    [string]$Store = "$PSScriptRoot/prototype_runs/seraph.sqlite",
    [string]$NewsStore = "$PSScriptRoot/prototype_runs/news-intelligence-pilot.sqlite",
    [string]$LiveStore = "$PSScriptRoot/prototype_runs/live.sqlite",
    [string]$NativeHawkesConfig = $env:SERAPH_NATIVE_HAWKES_CONFIG,
    [int]$Port = 8512,
    [switch]$NoNewsWorker,
    [switch]$NoMarketJobs,
    [switch]$NoLiveRuntime
)
$ErrorActionPreference = 'Stop'
$env:SERAPH_PROTOTYPE_STORE = $Store
$env:SERAPH_NEWS_STORE = $NewsStore
$env:SERAPH_LIVE_STORE = $LiveStore
if ($NativeHawkesConfig) {
    $env:SERAPH_NATIVE_HAWKES_CONFIG = (Resolve-Path -LiteralPath $NativeHawkesConfig).Path
}
$env:SERAPH_NEWS_WORKER = if ($NoNewsWorker) { '0' } else { '1' }

$Python = "$PSScriptRoot/.venv/Scripts/python.exe"
$Worker = $null
$Market = $null
$Live = $null
try {
    if (-not $NoMarketJobs) {
        New-Item -ItemType Directory -Force "$PSScriptRoot/prototype_runs" | Out-Null
        # Backgrounded on purpose. The daily RMT estimate takes about two
        # minutes (FR17 needs two endpoint windows and FR19 bootstraps each
        # 1,000 times), and blocking the console on it would mean staring at
        # a dead terminal before the page appears. The status file tells the
        # console what happened, and every step is idempotent so a relaunch
        # mid-run is harmless.
        $Market = Start-Process -FilePath $Python -ArgumentList @(
            "`"$PSScriptRoot/scripts/run_market_jobs.py`""
        ) -WorkingDirectory $PSScriptRoot -PassThru -WindowStyle Hidden `
          -RedirectStandardOutput "$PSScriptRoot/prototype_runs/market-jobs.log" `
          -RedirectStandardError "$PSScriptRoot/prototype_runs/market-jobs-errors.log"
        Write-Host "[seraph] market jobs pid $($Market.Id); log: prototype_runs/market-jobs.log"
    } else {
        Write-Host '[seraph] market jobs skipped for this run (-NoMarketJobs); stored vintages and forecasts are unchanged.'
    }
    if (-not $NoLiveRuntime) {
        New-Item -ItemType Directory -Force "$PSScriptRoot/prototype_runs" | Out-Null
        $Live = Start-Process -FilePath $Python -ArgumentList @(
            "`"$PSScriptRoot/scripts/run_live.py`"", '--stay-running',
            '--owner-pid', $PID, '--store', "`"$LiveStore`""
        ) -WorkingDirectory $PSScriptRoot -PassThru -WindowStyle Hidden `
          -RedirectStandardOutput "$PSScriptRoot/prototype_runs/live-runtime.log" `
          -RedirectStandardError "$PSScriptRoot/prototype_runs/live-runtime-errors.log"
        Write-Host "[seraph] owned market runtime pid $($Live.Id); log: prototype_runs/live-runtime.log"
    }
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
    # Only the processes this script started.
    if ($Live -and -not $Live.HasExited) {
        & taskkill /PID $Live.Id /T /F | Out-Null
    }
    if ($Worker -and -not $Worker.HasExited) {
        & taskkill /PID $Worker.Id /T /F | Out-Null
    }
    # The market jobs normally finish on their own well before shutdown;
    # this covers the case where the console is closed mid-run. Stopping it
    # loses no work: each step either committed its idempotent write or did
    # not, and the next launch repeats it.
    if ($Market -and -not $Market.HasExited) {
        & taskkill /PID $Market.Id /T /F | Out-Null
    }
}
