$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$ollamaExecutable=(Get-Command ollama).Source
$listeners=@(Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 1) {throw 'Multiple listeners; no process stopped.'}
if ($listeners.Count -eq 1) {
    $server=Get-CimInstance Win32_Process -Filter "ProcessId=$($listeners[0].OwningProcess)"
    if ($server.ExecutablePath -ne $ollamaExecutable -or $server.CommandLine -notmatch '\bserve\b') {throw 'Listener is not the expected local Ollama server.'}
    $children=@(Get-CimInstance Win32_Process | Where-Object {$_.ParentProcessId -eq $server.ProcessId})
    foreach ($child in $children) {
        if ($child.ExecutablePath -and $child.ExecutablePath.StartsWith((Split-Path -Parent $ollamaExecutable),[StringComparison]::OrdinalIgnoreCase)) {Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue}
    }
    Stop-Process -Id $server.ProcessId
}
Remove-Item Env:SSLKEYLOGFILE -ErrorAction SilentlyContinue
$env:OLLAMA_MODELS='F:\Ollama\models'
$env:OLLAMA_HOST='127.0.0.1:11434'
$env:OLLAMA_NUM_PARALLEL='1'
$env:OLLAMA_MAX_LOADED_MODELS='2'
$env:OLLAMA_NO_CLOUD='1'
$env:OLLAMA_NOPRUNE='1'
$env:LLAMA_ARG_CACHE_RAM='512'
$env:OLLAMA_CONTEXT_LENGTH='4096'
$logHistory=Join-Path $PWD '.cache/ollama-log-history'
New-Item -ItemType Directory -Force $logHistory | Out-Null
$logStamp=Get-Date -Format 'yyyyMMddTHHmmss'
foreach ($logName in @('ollama.stdout.log','ollama.stderr.log')) {
    if (Test-Path -LiteralPath (Join-Path $PWD $logName)) {Copy-Item -LiteralPath (Join-Path $PWD $logName) -Destination (Join-Path $logHistory "$logStamp-$logName")}
}
$serverProcess=Start-Process -FilePath $ollamaExecutable -ArgumentList 'serve' -WorkingDirectory $PWD -WindowStyle Hidden -RedirectStandardOutput "$PWD\ollama.stdout.log" -RedirectStandardError "$PWD\ollama.stderr.log" -PassThru
$serverProcess.Id | Set-Content .cache/ollama.pid
Write-Output 'Project Ollama restarted with F: model storage and 512 MiB prompt-cache cap.'
