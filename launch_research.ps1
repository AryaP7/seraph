param(
    [ValidateRange(1024, 65535)] [int]$Port = 8511,
    [string]$Results = 'research_results/v1_verified',
    [switch]$Headless
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv/Scripts/python.exe'
$appPath = Join-Path $projectRoot 'seraph/prediction/app.py'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'The experimental .venv is missing. See docs/HOW-TO-RESEARCH.md for setup.'
}
if ([System.IO.Path]::IsPathRooted($Results)) {
    $resultsPath = [System.IO.Path]::GetFullPath($Results)
} else {
    $resultsPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $Results))
}
$previousResults = $env:SERAPH_RESEARCH_RESULTS
$env:SERAPH_RESEARCH_RESULTS = $resultsPath
$headlessValue = if ($Headless) { 'true' } else { 'false' }
Push-Location -LiteralPath $projectRoot
try {
    Write-Host "Opening the local research viewer at http://127.0.0.1:$Port"
    Write-Host "Reading saved artifacts from $resultsPath"
    & $pythonExe -m streamlit run $appPath --server.address 127.0.0.1 --server.port $Port --server.headless $headlessValue --browser.gatherUsageStats false
    $runExitCode = $LASTEXITCODE
} finally {
    Pop-Location
    $env:SERAPH_RESEARCH_RESULTS = $previousResults
}
exit $runExitCode
