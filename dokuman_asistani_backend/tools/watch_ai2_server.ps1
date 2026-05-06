param(
  [string]$BindHost = "127.0.0.1",
  [int]$Port = 8002
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
$StdOutLog = Join-Path $RepoRoot "ai2_server_runtime.out.log"
$StdErrLog = Join-Path $RepoRoot "ai2_server_runtime.err.log"
$PidFile = Join-Path $RepoRoot "ai2_server_runtime.pid"

$serverPid = $null
if (Test-Path $PidFile) {
  $rawPid = Get-Content -Path $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($rawPid) {
    try { $serverPid = [int]$rawPid } catch { $serverPid = $null }
  }
}

$processInfo = $null
if ($serverPid) {
  $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $serverPid" -ErrorAction SilentlyContinue |
    Select-Object ProcessId,Name,CommandLine,CreationDate
}

$portOwner = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
  Sort-Object @{ Expression = { if ($_.State -eq "Listen") { 0 } else { 1 } } }, OwningProcess |
  Select-Object -First 1 LocalAddress,LocalPort,State,OwningProcess

$modelsOk = $false
$modelsStatus = ""
$chatOk = $false
$chatStatus = "models_not_ready"
$chatContentLength = 0
try {
  $resp = Invoke-WebRequest -Uri "http://$BindHost`:$Port/v1/models" -UseBasicParsing -TimeoutSec 5
  $modelsOk = ($resp.StatusCode -eq 200)
  $modelsStatus = "$($resp.StatusCode)"
} catch {
  $modelsOk = $false
  $modelsStatus = $_.Exception.Message
}

if ($modelsOk) {
  $payload = @{
    model = "qwen-docverse"
    messages = @(@{ role = "user"; content = "Merhaba. Tek kısa cümle cevap ver." })
    max_tokens = 32
    temperature = 0.1
  } | ConvertTo-Json -Depth 8 -Compress
  $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
  try {
    $chatResp = Invoke-RestMethod `
      -Uri "http://$BindHost`:$Port/v1/chat/completions" `
      -Method Post `
      -Body $bodyBytes `
      -ContentType "application/json; charset=utf-8" `
      -TimeoutSec 90
    $content = ""
    if ($chatResp.choices -and $chatResp.choices.Count -gt 0 -and $chatResp.choices[0].message) {
      $content = [string]$chatResp.choices[0].message.content
    }
    $chatOk = -not [string]::IsNullOrWhiteSpace($content)
    $chatStatus = "200"
    $chatContentLength = $content.Length
  } catch {
    $chatOk = $false
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
      $chatStatus = "$([int]$_.Exception.Response.StatusCode)"
    } else {
      $chatStatus = $_.Exception.Message
    }
  }
}

Write-Output "process_var_mi: $([bool]$processInfo)"
Write-Output "pid: $serverPid"
Write-Output "port_acik_mi: $([bool]$portOwner)"
Write-Output "models_ok_mu: $modelsOk"
Write-Output "models_durum: $modelsStatus"
Write-Output "chat_ok_mu: $chatOk"
Write-Output "chat_durum: $chatStatus"
Write-Output "chat_content_length: $chatContentLength"
if ($processInfo) {
  $processInfo | Format-List | Out-String | Write-Output
}
if ($portOwner) {
  $portOwner | Format-List | Out-String | Write-Output
}

Write-Output "----- stderr tail -----"
if (Test-Path $StdErrLog) {
  Get-Content -Path $StdErrLog -Tail 50
} else {
  Write-Output "stderr log yok"
}

Write-Output "----- stdout tail -----"
if (Test-Path $StdOutLog) {
  Get-Content -Path $StdOutLog -Tail 50
} else {
  Write-Output "stdout log yok"
}
