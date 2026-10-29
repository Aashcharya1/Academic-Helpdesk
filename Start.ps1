$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Remove-Item Env:SSLKEYLOGFILE -ErrorAction SilentlyContinue
$env:OLLAMA_MODELS = 'F:\Ollama\models'
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MAX_LOADED_MODELS = '2'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:LLAMA_ARG_CACHE_RAM = '512'
$env:OLLAMA_CONTEXT_LENGTH = '4096'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NOPRUNE = '1'
$env:OLLAMA_API_BASE = 'http://127.0.0.1:11434'
$env:ANONYMIZED_TELEMETRY = 'False'
$env:HF_HOME = Join-Path $PSScriptRoot '.cache\huggingface'
try { $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 }
catch { Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'ollama.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'ollama.stderr.log'); Start-Sleep -Seconds 3 }
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Project environment missing. Run Setup.ps1 first.' }
try { $uiReady = (Invoke-RestMethod 'http://127.0.0.1:8501/_stcore/health' -TimeoutSec 3) -eq 'ok' } catch { $uiReady = $false }
if (-not $uiReady) {
    Start-Process $python -ArgumentList @('-m','streamlit','run','app/main.py','--server.address','127.0.0.1','--server.port','8501','--server.headless','true','--browser.gatherUsageStats','false') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'ui.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'ui.stderr.log')
}
Start-Sleep -Seconds 3
Start-Process 'http://127.0.0.1:8501'
