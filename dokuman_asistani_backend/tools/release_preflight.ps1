param(
  [string]$PythonExe = "",
  [string]$ModelPath = "",
  [string]$DjangoBaseUrl = "http://127.0.0.1:8001",
  [string]$Ai2ModelsUrl = "http://127.0.0.1:8002/v1/models",
  [string]$TesseractPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Ok([string]$Message) {
  Write-Host "[OK]  $Message"
}

function Write-WarnLine([string]$Message) {
  Write-Host "[WARN] $Message"
}

function Resolve-PythonExe {
  param([string]$ExplicitPythonExe)

  $candidates = @(
    $ExplicitPythonExe,
    $env:DOCVERSE_PYTHON,
    $env:PYTHON_EXE,
    "C:\Users\cemre\miniconda3\envs\dj310_clean\python.exe"
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

  return $null
}

function Test-TcpPort([string]$HostName, [int]$Port) {
  try {
    $result = Test-NetConnection -ComputerName $HostName -Port $Port -WarningAction SilentlyContinue
    return [bool]$result.TcpTestSucceeded
  }
  catch {
    return $false
  }
}

function Test-HttpOk([string]$Url, [int]$TimeoutSec = 5) {
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
    return [bool]($response.StatusCode -ge 200 -and $response.StatusCode -lt 300)
  }
  catch {
    return $false
  }
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
    (Join-Path $RepoRoot "models\DeepSeek-R1-Distill-Qwen-7B-Q6_K_L.gguf"),
    "C:\Users\cemre\OneDrive\Desktop\ddd\Qwen2.5-7B-Instruct-Q5_K_M.gguf"
  ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }

  return $null
}

function Resolve-TesseractPath {
  param([string]$ExplicitTesseractPath)

  $candidates = @(
    $ExplicitTesseractPath,
    $env:TESSERACT_CMD,
    "C:\Program Files\Tesseract-OCR\tesseract.exe"
  ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }

  return $null
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$djangoUri = [Uri]$DjangoBaseUrl
$ai2Uri = [Uri]$Ai2ModelsUrl
$resolvedPythonExe = Resolve-PythonExe -ExplicitPythonExe $PythonExe
$resolvedModelPath = Resolve-ModelPath -ExplicitModelPath $ModelPath -RepoRoot $repoRoot
$resolvedTesseractPath = Resolve-TesseractPath -ExplicitTesseractPath $TesseractPath

Write-Host "Release preflight basliyor..."
Write-Host "repo=$repoRoot"

if (Test-Path -LiteralPath $repoRoot) {
  Write-Ok "Repo koku bulundu"
} else {
  throw "Repo koku bulunamadi: $repoRoot"
}

if (Test-Path -LiteralPath (Join-Path $repoRoot "manage.py")) {
  Write-Ok "manage.py bulundu"
} else {
  throw "manage.py bulunamadi"
}

if ($resolvedPythonExe) {
  $pythonVersion = & $resolvedPythonExe --version 2>&1
  Write-Ok "Python hazir: $pythonVersion ($resolvedPythonExe)"
} else {
  Write-WarnLine "Python bulunamadi. -PythonExe verin veya DOCVERSE_PYTHON ayarlayin."
}

if ($resolvedModelPath) {
  Write-Ok "GGUF bulundu: $resolvedModelPath"
} else {
  Write-WarnLine "GGUF bulunamadi. -ModelPath veya DOCVERSE_GGUF_PATH kullanin."
}

if ($resolvedTesseractPath) {
  Write-Ok "Tesseract bulundu: $resolvedTesseractPath"
} else {
  Write-WarnLine "Tesseract bulunamadi. -TesseractPath veya TESSERACT_CMD kullanin."
}

if (Test-Path -LiteralPath (Join-Path $repoRoot "test.docx")) {
  Write-Ok "Demo smoke dokumani hazir: test.docx"
} else {
  Write-WarnLine "Demo smoke dokumani yok: test.docx"
}

if (Test-Path -LiteralPath (Join-Path $repoRoot "ocr_test.png")) {
  Write-Ok "OCR demo girdisi hazir: ocr_test.png"
} else {
  Write-WarnLine "OCR demo girdisi yok: ocr_test.png"
}

$djangoPortOpen = Test-TcpPort -HostName $djangoUri.Host -Port $djangoUri.Port
if ($djangoPortOpen) {
  Write-Ok "Django port acik: $($djangoUri.Host):$($djangoUri.Port)"
} else {
  Write-WarnLine "Django port kapali: $($djangoUri.Host):$($djangoUri.Port)"
}

$ai2PortOpen = Test-TcpPort -HostName $ai2Uri.Host -Port $ai2Uri.Port
if ($ai2PortOpen) {
  Write-Ok "AI2 port acik: $($ai2Uri.Host):$($ai2Uri.Port)"
} else {
  Write-WarnLine "AI2 port kapali: $($ai2Uri.Host):$($ai2Uri.Port)"
}

if (Test-HttpOk -Url $Ai2ModelsUrl -TimeoutSec 5) {
  Write-Ok "AI2 /v1/models cevap veriyor"
} else {
  Write-WarnLine "AI2 /v1/models hazir degil: $Ai2ModelsUrl"
}

Write-Host ""
Write-Host "Portability notlari:"
Write-Host "- Bu script once explicit parametreleri, sonra ortam degiskenlerini, sonra dogrulanmis yerel yolu dener."
Write-Host "- Repo halen tam pinli production lockfile sunmuyor; dogrulanmis calisma profili ile dokumante edilen profil ayni sey degildir."
Write-Host "- GGUF repo disi olabilir; farkli makinede -ModelPath veya DOCVERSE_GGUF_PATH acik verilmelidir."
Write-Host "- OCR demolari icin Tesseract sistemde kurulu olmalidir."

Write-Host ""
Write-Host "Onerilen siradaki sonraki komutlar:"
if ($resolvedPythonExe) {
  Write-Host "1. & `"$resolvedPythonExe`" manage.py check"
  Write-Host "2. & `"$resolvedPythonExe`" .\\tools\\run_parser_ingestion_smoke.py"
  Write-Host "3. powershell -ExecutionPolicy Bypass -File .\\tools\\run_acceptance_sequential.ps1 -PythonExe `"$resolvedPythonExe`""
} else {
  Write-Host "1. -PythonExe vererek manage.py check kos"
  Write-Host "2. Ayni Python ile parser ingestion smoke kos"
  Write-Host "3. Ayni Python ile run_acceptance_sequential.ps1 kos"
}
Write-Host "4. Demo gerekiyorsa powershell -ExecutionPolicy Bypass -File .\\tools\\smoke_docverse_e2e.ps1 -Username cemre2 -Password 12345678 -FilePath .\\test.docx -BaseUrl $DjangoBaseUrl"
