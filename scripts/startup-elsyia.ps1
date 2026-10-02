$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"
$Python = Join-Path $BackendDir ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "logs"
$OllamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
$OllamaUrl = "http://127.0.0.1:11434/api/tags"
$BackendUrl = "http://127.0.0.1:8000/health"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogFile = Join-Path $LogDir "startup.log"

function Write-StartupLog([string]$Message) {
    Add-Content -Path $LogFile -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
}

function Test-Http([string]$Url) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

try {
    Write-StartupLog "Startup sequence beginning."

    if (-not (Test-Http $OllamaUrl)) {
        if (-not (Test-Path $OllamaExe)) {
            throw "Ollama executable not found at $OllamaExe"
        }
        if (-not (Get-Process -Name "ollama" -ErrorAction SilentlyContinue)) {
            Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden
            Write-StartupLog "Started Ollama server."
        }
    }

    $ollamaReady = $false
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-Http $OllamaUrl) {
            $ollamaReady = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $ollamaReady) {
        throw "Ollama did not become ready within 30 seconds"
    }
    Write-StartupLog "Ollama API is ready."

    if (-not (Test-Path $Python)) {
        throw "Backend Python environment not found at $Python"
    }
    if (-not (Test-Http $BackendUrl)) {
        Start-Process -FilePath $Python -ArgumentList "-m", "app.main" -WorkingDirectory $BackendDir -WindowStyle Hidden
        Write-StartupLog "Started Elsyia backend."
    }

    for ($i = 0; $i -lt 30; $i++) {
        if (Test-Http $BackendUrl) {
            Write-StartupLog "Elsyia backend is ready."
            exit 0
        }
        Start-Sleep -Seconds 1
    }
    throw "Elsyia backend did not become ready within 30 seconds"
} catch {
    Write-StartupLog ("Startup failed: " + $_.Exception.Message)
    exit 1
}
