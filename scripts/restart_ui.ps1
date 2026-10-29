$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$listeners=@(Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 1) {throw 'More than one listener; no process stopped.'}
if ($listeners.Count -eq 1) {
    $uiProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$($listeners[0].OwningProcess)"
    if ($uiProcess.CommandLine -notmatch 'streamlit.*app/main.py' -or $uiProcess.CommandLine -notmatch '8501') {throw 'Listener does not match this project UI.'}
    Stop-Process -Id $uiProcess.ProcessId
}
Remove-Item Env:SSLKEYLOGFILE -ErrorAction SilentlyContinue
$env:TIKTOKEN_CACHE_DIR=Join-Path $PWD '.cache/tiktoken'
$env:CUSTOM_TIKTOKEN_CACHE_DIR=$env:TIKTOKEN_CACHE_DIR
$startedUi=Start-Process -FilePath "$PWD\.venv\Scripts\python.exe" -ArgumentList @('-m','streamlit','run','app/main.py','--server.address','127.0.0.1','--server.port','8501','--server.headless','true','--browser.gatherUsageStats','false') -WorkingDirectory $PWD -WindowStyle Hidden -RedirectStandardOutput "$PWD\ui.stdout.log" -RedirectStandardError "$PWD\ui.stderr.log" -PassThru
$startedUi.Id | Set-Content .cache/ui.pid
Write-Output 'Project UI restarted without opening a browser.'
