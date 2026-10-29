$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Remove-Item Env:SSLKEYLOGFILE -ErrorAction SilentlyContinue
$env:PIP_CACHE_DIR = Join-Path $PSScriptRoot '.cache\pip'
$env:OLLAMA_MODELS = 'F:\Ollama\models'
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MAX_LOADED_MODELS = '2'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:LLAMA_ARG_CACHE_RAM = '512'
$env:OLLAMA_CONTEXT_LENGTH = '4096'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NOPRUNE = '1'
$env:TEMP = Join-Path $PSScriptRoot '.cache\tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', $env:OLLAMA_MODELS, 'User')
New-Item -ItemType Directory -Force $env:OLLAMA_MODELS | Out-Null
if (-not (Test-Path '.venv\Scripts\python.exe')) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'scripts/restart_ollama.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Could not configure the local Ollama server.' }
$ollamaReady=$false
for ($attempt=0; $attempt -lt 20; $attempt++) {
    try {$null=Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3; $ollamaReady=$true; break}
    catch {Start-Sleep -Seconds 1}
}
if (-not $ollamaReady) {throw 'Ollama did not become ready; inspect ollama.stderr.log.'}
foreach ($model in @('embeddinggemma:300m','qwen3:8b','llama3.1:8b')) { ollama pull $model; if ($LASTEXITCODE -ne 0) {throw "Model download failed: $model"} }
& .\.venv\Scripts\python.exe scripts/cache_tokenizer.py
& .\.venv\Scripts\python.exe -m helpdesk doctor --inference
if ($LASTEXITCODE -ne 0) {throw 'Model doctor failed.'}
$doctorResult=Get-Content -LiteralPath 'report/private/doctor.json' -Raw | ConvertFrom-Json
foreach ($model in @('qwen3:8b','llama3.1:8b')) {if (-not $doctorResult.$model.tool_call_verified) {throw "Actual tool inference was not verified: $model"}}
if ($doctorResult.embedding_probe.dimensions -ne 768) {throw 'Embedding inference was not verified.'}
