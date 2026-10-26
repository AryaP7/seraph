<#
    The REDESIGNED console. Classic is still the default.

        .\launch_redesign.ps1            # redesigned frontend, port 8520
        .\launch_prototype.ps1           # Classic, port 8512 — unchanged

    Returning to Classic is choosing the other launcher. There is nothing to
    revert and no database to restore: this frontend adds files
    (seraph/dashboard/redesign/**) and edits none of Classic's.

    BOTH AT ONCE. Safe, and deliberately so. The two frontends read the same
    stores and must not both run the background work.

      * News acquisition. The worker is a property of the application, not of
        a launcher: the app calls `news_service.ensure_worker()` on first page
        view, which probes the OS lock in `seraph/news/worker_lock.py` and
        stands aside when a supervisor already holds the store. Whichever
        frontend reaches it first owns the worker; the other says on screen
        that it did not start one. This launcher therefore starts NO
        supervisor of its own -- unlike launch_prototype.ps1, which starts one
        eagerly so that a server with no browser session attached still
        fetches.

      * Market jobs and the owned market runtime. NOT started here at all.
        launch_prototype.ps1 owns them. Running a second copy would mean two
        processes writing the same vintages and the same live store, and the
        locks that cover the news worker do not cover the market jobs. If you
        are running ONLY the redesigned frontend and want them, pass
        -WithMarketJobs / -WithLiveRuntime, and then do not also run
        launch_prototype.ps1.

    So: launch Classic for the full runtime, and launch this alongside it to
    read the same stores through the redesigned screens.

    -NoNewsWorker sets SERAPH_NEWS_WORKER=0, so this app will not start a
    worker even when the lock is free. The screen then says nothing is
    fetching, which is true.
#>
param(
    [string]$Store = $env:SERAPH_PROTOTYPE_STORE,
    [string]$NewsStore = "$PSScriptRoot/prototype_runs/news-intelligence-pilot.sqlite",
    [string]$LiveStore = "$PSScriptRoot/prototype_runs/live.sqlite",
    [int]$Port = 8520,
    [switch]$NoNewsWorker,
    [switch]$WithMarketJobs,
    [switch]$WithLiveRuntime
)
$ErrorActionPreference = 'Stop'

# An unset -Store leaves SERAPH_PROTOTYPE_STORE exactly as the machine has it,
# so both frontends resolve the same archive. `store_paths()` is imported from
# the Classic app rather than reimplemented, for the same reason.
if ($Store) { $env:SERAPH_PROTOTYPE_STORE = $Store }
$env:SERAPH_NEWS_STORE = $NewsStore
$env:SERAPH_LIVE_STORE = $LiveStore
$env:SERAPH_NEWS_WORKER = if ($NoNewsWorker) { '0' } else { '1' }

$Python = "$PSScriptRoot/.venv/Scripts/python.exe"
$Market = $null
$Live = $null
try {
    if ($WithMarketJobs) {
        Write-Host '[seraph/redesign] -WithMarketJobs: do NOT also run launch_prototype.ps1.'
        New-Item -ItemType Directory -Force "$PSScriptRoot/prototype_runs" | Out-Null
        $Market = Start-Process -FilePath $Python -ArgumentList @(
            "`"$PSScriptRoot/scripts/run_market_jobs.py`""
        ) -WorkingDirectory $PSScriptRoot -PassThru -WindowStyle Hidden `
          -RedirectStandardOutput "$PSScriptRoot/prototype_runs/market-jobs.log" `
          -RedirectStandardError "$PSScriptRoot/prototype_runs/market-jobs-errors.log"
        Write-Host "[seraph/redesign] market jobs pid $($Market.Id)"
    }
    if ($WithLiveRuntime) {
        Write-Host '[seraph/redesign] -WithLiveRuntime: do NOT also run launch_prototype.ps1.'
        New-Item -ItemType Directory -Force "$PSScriptRoot/prototype_runs" | Out-Null
        $Live = Start-Process -FilePath $Python -ArgumentList @(
            "`"$PSScriptRoot/scripts/run_live.py`"", '--stay-running',
            '--owner-pid', $PID, '--store', "`"$LiveStore`""
        ) -WorkingDirectory $PSScriptRoot -PassThru -WindowStyle Hidden `
          -RedirectStandardOutput "$PSScriptRoot/prototype_runs/live-runtime.log" `
          -RedirectStandardError "$PSScriptRoot/prototype_runs/live-runtime-errors.log"
        Write-Host "[seraph/redesign] owned market runtime pid $($Live.Id)"
    }
    Write-Host "[seraph/redesign] redesigned console on http://127.0.0.1:$Port"
    Write-Host '[seraph/redesign] Classic is unchanged: .\launch_prototype.ps1 (port 8512).'
    & $Python -m streamlit run "$PSScriptRoot/seraph/dashboard/redesign/app.py" `
        --server.address 127.0.0.1 --server.port $Port --server.headless true
} finally {
    # Only the processes this script started.
    if ($Live -and -not $Live.HasExited) { & taskkill /PID $Live.Id /T /F | Out-Null }
    if ($Market -and -not $Market.HasExited) { & taskkill /PID $Market.Id /T /F | Out-Null }
}
