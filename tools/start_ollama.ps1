# Portable local AI runtime. No global environment or Windows service is changed.
$ErrorActionPreference = 'Stop'
$candidates = @(
    @{ Root = 'E:\Ollama'; Runtime = 'runtime-store\Ollama\ollama.exe'; Models = 'models-store' },
    @{ Root = 'E:\ShortPilot-AI\Ollama'; Runtime = 'runtime\ollama.exe'; Models = 'models' }
)
$selected = $candidates | Where-Object {
    Test-Path -LiteralPath (Join-Path $_.Root $_.Runtime)
} | Select-Object -First 1
if ($null -eq $selected) { exit 0 }
$studioAiRoot = $selected.Root
$studioAiExe = Join-Path $studioAiRoot $selected.Runtime
$studioModels = Join-Path $studioAiRoot $selected.Models
try {
    Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2 | Out-Null
    exit 0
} catch {}
$env:OLLAMA_MODELS = $studioModels
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_CONTEXT_LENGTH = '8192'
$env:OLLAMA_KEEP_ALIVE = '2m'
Start-Process -FilePath $studioAiExe -ArgumentList 'serve' -WorkingDirectory $studioAiRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $studioAiRoot 'server.stdout.log') -RedirectStandardError (Join-Path $studioAiRoot 'server.stderr.log') | Out-Null
