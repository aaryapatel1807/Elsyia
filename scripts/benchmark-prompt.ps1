$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$model = "qwen2.5:1.5b"
$question = "What is 2 plus 2? Answer in one short sentence."
$currentPrompt = Get-Content (Join-Path $project "prompts\elysia.txt") -Raw
$previousPrompt = git -C $project show HEAD:prompts/elysia.txt

function Invoke-Ollama([string]$SystemPrompt) {
    $body = @{
        model = $model
        messages = @(
            @{ role = "system"; content = $SystemPrompt },
            @{ role = "user"; content = $question }
        )
        stream = $false
        keep_alive = "30m"
        options = @{
            temperature = 0.2
            num_predict = 32
            num_ctx = 2048
        }
    } | ConvertTo-Json -Depth 6
    $started = [Diagnostics.Stopwatch]::StartNew()
    $response = Invoke-RestMethod -UseBasicParsing -Uri "http://127.0.0.1:11434/api/chat" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 30
    $started.Stop()
    [pscustomobject]@{
        wall_ms = $started.ElapsedMilliseconds
        prompt_chars = $SystemPrompt.Length
        prompt_eval_ms = [math]::Round($response.prompt_eval_duration / 1000000, 1)
        eval_ms = [math]::Round($response.eval_duration / 1000000, 1)
        total_ms = [math]::Round($response.total_duration / 1000000, 1)
        response = $response.message.content
    }
}

Write-Output "warming model"
Invoke-Ollama $currentPrompt | Out-Null
Write-Output "previous prompt"
Invoke-Ollama $previousPrompt | Format-List
Write-Output "compact prompt run 1"
Invoke-Ollama $currentPrompt | Format-List
Write-Output "compact prompt run 2"
Invoke-Ollama $currentPrompt | Format-List
Write-Output "compact prompt run 3"
Invoke-Ollama $currentPrompt | Format-List
