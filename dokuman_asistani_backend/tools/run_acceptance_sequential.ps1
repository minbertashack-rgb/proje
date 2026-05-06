param(
  [string]$PythonExe = "",
  [string[]]$Suites = @("suite_a", "suite_b", "suite_c"),
  [ValidateSet("legacy_suites", "release_shards")]
  [string]$Mode = "legacy_suites",
  [string[]]$ReleaseShards = @("upload_ingestion_ocr", "explain_evidence_ai", "api_security_notes"),
  [int]$PerSuiteTimeoutSec = 1800,
  [string]$OutputDir = "",
  [int]$InterSuitePauseSec = 3,
  [switch]$ListOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

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

  throw "Python bulunamadi. -PythonExe verin veya DOCVERSE_PYTHON ayarlayin."
}

function Get-PytestProcessesForRepo {
  param([string]$RepoRoot)

  Get-CimInstance Win32_Process |
    Where-Object {
      $cmd = $_.CommandLine
      $cmd -and
      $cmd -like "*-m pytest*" -and
      $cmd -like "*$RepoRoot*"
    }
}

function Stop-PytestProcessesForRepo {
  param([string]$RepoRoot)

  $targets = @(Get-PytestProcessesForRepo -RepoRoot $RepoRoot)
  foreach ($target in $targets) {
    if ($target.ProcessId -ne $PID) {
      Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
    }
  }
}

function Write-StatusLine {
  param(
    [string]$Label,
    [string]$Message
  )

  Write-Host "[$Label] $Message"
}

function Show-LogTail {
  param(
    [string]$Label,
    [string]$Path,
    [int]$Tail = 20
  )

  if (Test-Path -LiteralPath $Path) {
    Write-Host "----- $Label ($Path) -----"
    Get-Content -LiteralPath $Path -Tail $Tail
  }
}

function New-ReleaseShardDefinitions {
  return @{
    upload_ingestion_ocr = [pscustomobject]@{
      Name = "upload_ingestion_ocr"
      Protects = "upload contract, suspicious upload reddi, parser/ingestion, OCR fallback ve OCR signal"
      Files = @(
        "dokuman/tests/test_upload_fields.py",
        "dokuman/tests/test_ocr_ingestion.py",
        "dokuman/tests/test_multiformat_ingestion.py",
        "dokuman/tests/test_ingestion_contract.py",
        "dokuman/tests/test_ingestion_quality.py",
        "dokuman/tests/test_golden_parser_ingestion.py"
      )
    }
    explain_evidence_ai = [pscustomobject]@{
      Name = "explain_evidence_ai"
      Protects = "explain/anlamadim kalite floor'u, evidence alignment, abstain, AI2 no-leak"
      Files = @(
        "dokuman/tests/test_anlamadim_quality.py",
        "dokuman/tests/test_special_chunk_explanations.py",
        "dokuman/tests/test_rag_quality.py",
        "dokuman/tests/test_rag_normalization.py",
        "dokuman/tests/test_ai2_guardrails.py",
        "dokuman/tests/test_ai2_runtime_tools.py",
        "dokuman/tests/test_ai_eval_contracts.py"
      )
    }
    api_security_notes = [pscustomobject]@{
      Name = "api_security_notes"
      Protects = "auth/api contract, notes/history, throttle 429 payload, ownership isolation, no-leak"
      Files = @(
        "dokuman/tests/test_patch2_auth_error_shapes.py",
        "dokuman/tests/test_patch3_explain_evidence_notes_shapes.py",
        "dokuman/tests/test_patch6_throttle_shapes.py",
        "dokuman/tests/test_views_hardening.py",
        "dokuman/tests/test_notlar_productization.py",
        "dokuman/tests/test_phase4_5_surfaces.py",
        "dokuman/tests/test_export_readiness.py"
      )
    }
  }
}

function Get-RunDefinitions {
  param(
    [string]$SelectedMode,
    [string[]]$LegacySuites,
    [string[]]$SelectedReleaseShards
  )

  if ($SelectedMode -eq "release_shards") {
    $shardDefinitions = New-ReleaseShardDefinitions
    $runs = @()
    foreach ($shardName in $SelectedReleaseShards) {
      if (-not $shardDefinitions.ContainsKey($shardName)) {
        throw "Bilinmeyen release shard: $shardName"
      }
      $shard = $shardDefinitions[$shardName]
      $runs += [pscustomobject]@{
        name = $shard.Name
        mode = "release_shard"
        protects = $shard.Protects
        pytest_args = @($shard.Files)
      }
    }
    return $runs
  }

  return @(
    $LegacySuites | ForEach-Object {
      [pscustomobject]@{
        name = $_
        mode = "legacy_suite"
        protects = "legacy pytest marker shard"
        pytest_args = @("-m", $_)
      }
    }
  )
}

function Invoke-TestRun {
  param(
    [string]$RunName,
    [string[]]$PytestArgs,
    [string]$PythonPath,
    [string]$RepoRoot,
    [string]$RunOutputDir,
    [int]$TimeoutSec
  )

  $safeName = $RunName -replace "[^A-Za-z0-9_.-]", "_"
  $stdoutPath = Join-Path $RunOutputDir "$safeName.stdout.log"
  $stderrPath = Join-Path $RunOutputDir "$safeName.stderr.log"
  $startedAt = Get-Date
  $pytestArgText = ($PytestArgs | ForEach-Object { $_ }) -join " "
  $cmdArgs = '/d /c ""{0}" -m pytest -q {1} 1> "{2}" 2> "{3}""' -f $PythonPath, $pytestArgText, $stdoutPath, $stderrPath
  $process = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList $cmdArgs `
    -WorkingDirectory $RepoRoot `
    -PassThru `
    -WindowStyle Hidden

  if ($TimeoutSec -gt 0) {
    $finished = $process.WaitForExit($TimeoutSec * 1000)
  } else {
    $process.WaitForExit()
    $finished = $true
  }

  if (-not $finished) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    $process.WaitForExit()
    Start-Sleep -Seconds 1
    Stop-PytestProcessesForRepo -RepoRoot $RepoRoot

    return [pscustomobject]@{
      suite = $RunName
      classification = "environment_timeout"
      exit_code = 124
      duration_sec = [math]::Round(((Get-Date) - $startedAt).TotalSeconds, 2)
      stdout = $stdoutPath
      stderr = $stderrPath
      timed_out = $true
    }
  }

  $process.WaitForExit()
  $process.Refresh()
  $exitCode = $process.ExitCode
  $stdoutContent = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw } else { "" }
  $stderrContent = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw } else { "" }
  $hasPytestSummary = ($stdoutContent -match '\b\d+\s+passed\b') -or ($stdoutContent -match '\b\d+\s+failed\b') -or ($stdoutContent -match '\b\d+\s+error') -or ($stdoutContent -match '\bno tests ran\b')

  if ($exitCode -eq 0) {
    $classification = "passed"
  } elseif (($exitCode -eq -1) -and (-not $hasPytestSummary) -and [string]::IsNullOrWhiteSpace($stderrContent)) {
    $classification = "environment_interruption"
  } elseif ((-not $hasPytestSummary) -and [string]::IsNullOrWhiteSpace($stderrContent)) {
    $classification = "environment_interruption"
  } else {
    $classification = "deterministic_regression"
  }

  return [pscustomobject]@{
    suite = $RunName
    classification = $classification
    exit_code = $exitCode
    duration_sec = [math]::Round(((Get-Date) - $startedAt).TotalSeconds, 2)
    stdout = $stdoutPath
    stderr = $stderrPath
    timed_out = $false
  }
}

$repoRoot = (Resolve-Path ".").Path
$resolvedPythonExe = Resolve-PythonExe -ExplicitPythonExe $PythonExe
$runDefinitions = @(Get-RunDefinitions -SelectedMode $Mode -LegacySuites $Suites -SelectedReleaseShards $ReleaseShards)

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
  $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $OutputDir = Join-Path $repoRoot "acceptance_logs\$timestamp"
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$results = @()

Write-StatusLine -Label "INFO" -Message "Repo: $repoRoot"
Write-StatusLine -Label "INFO" -Message "Python: $resolvedPythonExe"
Write-StatusLine -Label "INFO" -Message "Mode: $Mode"
if ($Mode -eq "release_shards") {
  Write-StatusLine -Label "INFO" -Message "Release shards: $($ReleaseShards -join ', ')"
} else {
  Write-StatusLine -Label "INFO" -Message "Suites: $($Suites -join ', ')"
}
Write-StatusLine -Label "INFO" -Message "Per-suite timeout: $PerSuiteTimeoutSec sn"
Write-StatusLine -Label "INFO" -Message "Inter-suite pause: $InterSuitePauseSec sn"
Write-StatusLine -Label "INFO" -Message "Log dizini: $OutputDir"

if ($ListOnly) {
  Write-Host ""
  Write-Host "=== Acceptance Plan ==="
  foreach ($run in $runDefinitions) {
    Write-Host ("{0} | mode={1}" -f $run.name, $run.mode)
    Write-Host ("  protects={0}" -f $run.protects)
    Write-Host ("  pytest_args={0}" -f ($run.pytest_args -join " "))
  }
  exit 0
}

@{
  mode = $Mode
  runs = @(
    $runDefinitions | ForEach-Object {
      @{
        name = $_.name
        mode = $_.mode
        protects = $_.protects
        pytest_args = @($_.pytest_args)
      }
    }
  )
} | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $OutputDir "acceptance_plan.json") -Encoding UTF8

try {
  Stop-PytestProcessesForRepo -RepoRoot $repoRoot

  foreach ($run in $runDefinitions) {
    Write-Host ""
    Write-StatusLine -Label "RUN" -Message "$($run.name) basliyor"
    Write-StatusLine -Label "INFO" -Message "Korudugu yuzey: $($run.protects)"
    $result = Invoke-TestRun `
      -RunName $run.name `
      -PytestArgs $run.pytest_args `
      -PythonPath $resolvedPythonExe `
      -RepoRoot $repoRoot `
      -RunOutputDir $OutputDir `
      -TimeoutSec $PerSuiteTimeoutSec

    $results += $result

    if ($result.classification -eq "passed") {
      Write-StatusLine -Label "PASS" -Message "$($run.name) tamamlandi ($($result.duration_sec) sn)"
      Stop-PytestProcessesForRepo -RepoRoot $repoRoot
      if ($InterSuitePauseSec -gt 0) {
        Start-Sleep -Seconds $InterSuitePauseSec
      }
      continue
    }

    if ($result.classification -eq "environment_timeout") {
      Write-StatusLine -Label "FAIL" -Message "$($run.name) timeout oldu ($($result.duration_sec) sn)"
      Show-LogTail -Label "$($run.name) stderr" -Path $result.stderr
      Show-LogTail -Label "$($run.name) stdout" -Path $result.stdout
      break
    }

    if ($result.classification -eq "environment_interruption") {
      Write-StatusLine -Label "FAIL" -Message "$($run.name) ortam kesintisi ile durdu (exit=$($result.exit_code))"
      Show-LogTail -Label "$($run.name) stderr" -Path $result.stderr
      Show-LogTail -Label "$($run.name) stdout" -Path $result.stdout
      break
    }

    Write-StatusLine -Label "FAIL" -Message "$($run.name) pytest hatasi verdi (exit=$($result.exit_code))"
    Show-LogTail -Label "$($run.name) stderr" -Path $result.stderr
    Show-LogTail -Label "$($run.name) stdout" -Path $result.stdout
    break
  }
}
finally {
  Stop-PytestProcessesForRepo -RepoRoot $repoRoot
}

Write-Host ""
Write-Host "=== Acceptance Ozeti ==="
foreach ($result in $results) {
  Write-Host ("{0} | class={1} | exit={2} | sure={3} sn" -f $result.suite, $result.classification, $result.exit_code, $result.duration_sec)
  Write-Host ("  stdout={0}" -f $result.stdout)
  Write-Host ("  stderr={0}" -f $result.stderr)
}

Write-Host ""
Write-Host "=== EVIDENCE ARTIFACTS GENERATED ==="
Write-Host "Kapanis (Closure) kanitlari su dizinde toplanmistir: $OutputDir"
Write-Host "Plan dosyasi: $(Join-Path $OutputDir 'acceptance_plan.json')"
Write-Host "Lutfen FINAL_CLOSURE_SCORECARD.md dokumanindaki metriklerle bu loglari eslestirin."

$failed = $results | Where-Object { $_.classification -ne "passed" } | Select-Object -First 1
if ($failed) {
  exit $failed.exit_code
}

exit 0
