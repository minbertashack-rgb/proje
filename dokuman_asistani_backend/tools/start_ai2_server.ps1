param(
  [switch]$ForceRestart = $true,
  [string]$PythonExe = "",
  [string]$ModelPath = "",
  [string]$BindHost = "127.0.0.1",
  [int]$Port = 8002,
  [int]$ReadyTimeoutSec = 240,
  [int]$PollIntervalSec = 5,
  [int]$NCtx = 1024,
  [int]$NThreads = 8,
  [int]$NGpuLayers = 0,
  [string]$ChatFormat = "",
  [string]$ModelAlias = "qwen-docverse"
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
$StdOutLog = Join-Path $RepoRoot "ai2_server_runtime.out.log"
$StdErrLog = Join-Path $RepoRoot "ai2_server_runtime.err.log"
$PidFile = Join-Path $RepoRoot "ai2_server_runtime.pid"

function Resolve-PythonExe {
  param(
    [string]$ExplicitPythonExe,
    [string]$RepoRoot
  )

  $candidates = @(
    $ExplicitPythonExe,
    $env:DOCVERSE_PYTHON,
    $env:PYTHON_EXE,
    (Join-Path $RepoRoot ".conda\python.exe"),
    (Join-Path $RepoRoot ".venv\Scripts\python.exe")
  ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }

  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCommand -and $pythonCommand.Source -and (Test-Path -LiteralPath $pythonCommand.Source)) {
    return (Resolve-Path -LiteralPath $pythonCommand.Source).Path
  }

  throw "Python bulunamadi. -PythonExe verin veya DOCVERSE_PYTHON ayarlayin."
}

function Resolve-ModelPath {
  param(
    [string]$ExplicitModelPath,
    [string]$RepoRoot
  )

  $candidates = @(
    $ExplicitModelPath,
    $env:DOCVERSE_GGUF_PATH,
    $env:ANA_GGUF_YOLU,
    $env:YEREL_MODEL_YOLU,
    (Join-Path $RepoRoot "models\Qwen2.5-7B-Instruct-Q5_K_M.gguf"),
    (Join-Path $RepoRoot "models\Qwen2.5-7B-Instruct-Q4_K_S.gguf"),
    (Join-Path $RepoRoot "models\DeepSeek-R1-Distill-Qwen-7B-Q6_K_L.gguf")
  ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }

  $joined = ($candidates | Select-Object -Unique) -join "; "
  throw "Model bulunamadi. Yeni varsayilan Q5_K_M GGUF'tur. Denenen yollar: $joined"
}

function Get-AI2PortOwner {
  Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Sort-Object @{ Expression = { if ($_.State -eq "Listen") { 0 } else { 1 } } }, OwningProcess |
    Select-Object -First 1 LocalAddress, LocalPort, State, OwningProcess
}

function Get-ProcessInfo($ProcessId) {
  Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue |
    Select-Object ProcessId, Name, CommandLine, CreationDate
}

function Get-LlamaCppSystemInfo {
  param([string]$PythonExe)

  try {
    $info = & $PythonExe -c "from llama_cpp import llama_cpp; print(llama_cpp.llama_print_system_info().decode('utf-8', errors='replace'))" 2>$null
    return ($info -join " ").Trim()
  } catch {
    return "llama_cpp sistem bilgisi okunamadi: $($_.Exception.Message)"
  }
}

function Invoke-AI2ChatSmoke {
  param(
    [string]$BindHost,
    [int]$Port,
    [string]$ModelAlias
  )

  $payload = @{
    model = $ModelAlias
    messages = @(@{ role = "user"; content = "Merhaba. Tek kısa cümle cevap ver." })
    max_tokens = 32
    temperature = 0.1
  } | ConvertTo-Json -Depth 8 -Compress

  $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
  try {
    $response = Invoke-RestMethod `
      -Uri "http://$BindHost`:$Port/v1/chat/completions" `
      -Method Post `
      -Body $bodyBytes `
      -ContentType "application/json; charset=utf-8" `
      -TimeoutSec 90
    $content = ""
    if ($response.choices -and $response.choices.Count -gt 0 -and $response.choices[0].message) {
      $content = [string]$response.choices[0].message.content
    }
    return @{
      ok = -not [string]::IsNullOrWhiteSpace($content)
      status = "200"
      content_length = $content.Length
    }
  } catch {
    $status = ""
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
      $status = [int]$_.Exception.Response.StatusCode
    }
    if (-not $status) {
      $status = $_.Exception.Message
    }
    return @{
      ok = $false
      status = "$status"
      content_length = 0
    }
  }
}

$existing = Get-AI2PortOwner
if ($existing) {
  $processInfo = Get-ProcessInfo $existing.OwningProcess
  Write-Output "Mevcut 8002 sureci bulundu:"
  $existing | Format-List | Out-String | Write-Output
  $processInfo | Format-List | Out-String | Write-Output

  if ($ForceRestart -and $existing.OwningProcess) {
    Stop-Process -Id $existing.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  } else {
    Write-Output "ForceRestart kapali. Yeni server baslatilmadi."
    exit 1
  }
}

$resolvedPythonExe = Resolve-PythonExe -ExplicitPythonExe $PythonExe -RepoRoot $RepoRoot
$resolvedModelPath = Resolve-ModelPath -ExplicitModelPath $ModelPath -RepoRoot $RepoRoot
$llamaSystemInfo = Get-LlamaCppSystemInfo -PythonExe $resolvedPythonExe
$gpuBuildHint = if ($llamaSystemInfo -match "CUDA|CUBLAS|HIP|ROCM|METAL|VULKAN|SYCL") { "gpu-capable" } else { "cpu-only-or-unknown" }

if ($NGpuLayers -ne 0 -and $gpuBuildHint -eq "cpu-only-or-unknown") {
  Write-Output "UYARI: llama-cpp-python build GPU backend bilgisi gostermiyor. NGpuLayers=$NGpuLayers ile baslatma denenir; destek yoksa CPU modunda -NGpuLayers 0 kullanin."
}

$env:PYTHONIOENCODING = "utf-8"
$arguments = @(
  "-m", "llama_cpp.server",
  "--host", $BindHost,
  "--port", "$Port",
  "--model", $resolvedModelPath,
  "--model_alias", $ModelAlias,
  "--n_ctx", "$NCtx",
  "--n_threads", "$NThreads",
  "--n_gpu_layers", "$NGpuLayers"
)
if (-not [string]::IsNullOrWhiteSpace($ChatFormat)) {
  $arguments += @("--chat_format", $ChatFormat)
}

$process = Start-Process `
  -FilePath $resolvedPythonExe `
  -ArgumentList $arguments `
  -WorkingDirectory $RepoRoot `
  -RedirectStandardOutput $StdOutLog `
  -RedirectStandardError $StdErrLog `
  -PassThru `
  -WindowStyle Hidden

$process.Id | Set-Content -Path $PidFile -Encoding ascii
$startedAt = Get-Date
$modelsOk = $false
$modelsStatus = ""
$chatOk = $false
$chatStatus = "models_not_ready"
$chatContentLength = 0
$startupWaitSec = 0
$deadline = $startedAt.AddSeconds([Math]::Max(10, $ReadyTimeoutSec))
while ((Get-Date) -lt $deadline) {
  $portOwner = Get-AI2PortOwner
  try {
    $resp = Invoke-WebRequest -Uri "http://$BindHost`:$Port/v1/models" -UseBasicParsing -TimeoutSec ([Math]::Max(3, $PollIntervalSec))
    $modelsOk = ($resp.StatusCode -eq 200)
    $modelsStatus = "$($resp.StatusCode)"
    if ($modelsOk) { break }
  }
  catch {
    $modelsStatus = $_.Exception.Message
  }

  if ($process.HasExited) {
    break
  }
  Start-Sleep -Seconds ([Math]::Max(2, $PollIntervalSec))
}
$startupWaitSec = [math]::Round(((Get-Date) - $startedAt).TotalSeconds, 2)
$portOwner = Get-AI2PortOwner
$process.Refresh()
$processExitedEarly = $process.HasExited -and (-not $modelsOk)
if ($modelsOk -and -not $process.HasExited) {
  $chatSmoke = Invoke-AI2ChatSmoke -BindHost $BindHost -Port $Port -ModelAlias $ModelAlias
  $chatOk = [bool]$chatSmoke.ok
  $chatStatus = [string]$chatSmoke.status
  $chatContentLength = [int]$chatSmoke.content_length
}

Write-Output "AI2 server baslatildi."
Write-Output "PID: $($process.Id)"
Write-Output "Python: $resolvedPythonExe"
Write-Output "Model: $resolvedModelPath"
Write-Output "Host: $BindHost"
Write-Output "Port: $Port"
Write-Output "n_ctx: $NCtx"
Write-Output "n_threads: $NThreads"
Write-Output "n_gpu_layers: $NGpuLayers"
Write-Output "chat_format: $ChatFormat"
Write-Output "llama_cpp_build: $gpuBuildHint"
Write-Output "llama_cpp_system_info: $llamaSystemInfo"
Write-Output "Alias: $ModelAlias"
Write-Output "stdout: $StdOutLog"
Write-Output "stderr: $StdErrLog"
Write-Output "pid_file: $PidFile"
Write-Output "ready_timeout_sec: $ReadyTimeoutSec"
Write-Output "startup_wait_sec: $startupWaitSec"
Write-Output "port_acik_mi: $([bool]$portOwner)"
Write-Output "models_ok_mu: $modelsOk"
Write-Output "models_durum: $modelsStatus"
Write-Output "chat_ok_mu: $chatOk"
Write-Output "chat_durum: $chatStatus"
Write-Output "chat_content_length: $chatContentLength"
Write-Output "process_exited_early: $processExitedEarly"

if ((-not $modelsOk) -or (-not $chatOk)) {
  Write-Output "----- stderr tail -----"
  if (Test-Path $StdErrLog) {
    Get-Content -Path $StdErrLog -Tail 40
  }
  Write-Output "----- stdout tail -----"
  if (Test-Path $StdOutLog) {
    Get-Content -Path $StdOutLog -Tail 20
  }
  if ($NGpuLayers -ne 0) {
    Write-Output "GPU notu: NGpuLayers=$NGpuLayers ile baslatma basarisizsa llama-cpp-python build CPU-only olabilir. CPU fallback icin -NGpuLayers 0 ile tekrar baslatin."
  }
}
