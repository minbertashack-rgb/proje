# Release Acceptance Checklist

Bu dokuman hizli gate, release shard ve E2E smoke akisini tek sayfada toplar.

## Demo OK vs Release OK

`demo_ok`:

- temel auth -> upload -> parca listesi zinciri calisiyor
- `anlamadim-v2` temel smoke temiz
- gerekiyorsa tek bir OCR veya retrieval gosteri akisi calisiyor

`release_ok`:

- `python tools/run_release_gate.py` temiz veya yalnizca operasyon notlu
- `python tools/release_checks.py` sonucu `no_ship` degil
- release shard kosusu temiz
- gerekli E2E smoke probelari temiz
- must-pass acceptance alanlarinda fail yok

Demo temiz gecse bile release otomatik temiz sayilmaz.

## Release Shard Plani

`upload_ingestion_ocr`

- `test_upload_fields.py`
- `test_ocr_ingestion.py`
- `test_multiformat_ingestion.py`
- `test_ingestion_contract.py`
- `test_ingestion_quality.py`
- `test_golden_parser_ingestion.py`

Korudugu yuzey:

- upload kontrati
- suspicious upload reddi
- parser/ingestion
- OCR fallback ve OCR signal
- multiformat acceptance

`explain_evidence_ai`

- `test_anlamadim_quality.py`
- `test_special_chunk_explanations.py`
- `test_rag_quality.py`
- `test_rag_normalization.py`
- `test_ai2_guardrails.py`
- `test_ai2_runtime_tools.py`
- `test_ai_eval_contracts.py`

Korudugu yuzey:

- explain/anlamadim kalite floor'u
- weak/strong evidence ayrimi
- abstain davranisi
- AI2 no-leak ve runtime guardrail

`api_security_notes`

- `test_patch2_auth_error_shapes.py`
- `test_patch3_explain_evidence_notes_shapes.py`
- `test_patch6_throttle_shapes.py`
- `test_views_hardening.py`
- `test_notlar_productization.py`
- `test_phase4_5_surfaces.py`
- `test_export_readiness.py`

Korudugu yuzey:

- auth/api contract
- notes/history envelope
- throttle 429 payload
- ownership isolation
- no-leak ve views hardening

## Kosu Sirasi

1. `python tools/release_checks.py`
2. `python tools/run_release_gate.py`
3. `powershell -ExecutionPolicy Bypass -File .\tools\run_acceptance_sequential.ps1 -Mode release_shards -PythonExe $env:DOCVERSE_PYTHON`
4. gerekiyorsa `powershell -ExecutionPolicy Bypass -File .\tools\run_acceptance_sequential.ps1 -PythonExe $env:DOCVERSE_PYTHON`
5. `powershell -ExecutionPolicy Bypass -File .\tools\smoke_docverse_e2e.ps1 ...`

## E2E Smoke Probelari

Temel smoke:

- auth -> upload -> parca listesi
- parca -> `anlamadim-v2`

Opsiyonel release probelari:

- `-ExpectOcrSignal`
- `-ProbeEvidence`
- `-ProbeNotes`
- `-ProbeForeignAccess -SecondaryUsername ... -SecondaryPassword ...`
- `-ProbeThrottle`

Throttle probe yalnizca throttle limiti dusuk ortamda karar verdiricidir. Gerekirse `-RequireThrottleHit` ile zorunlu hale getirilmelidir.

## Final Karar

- `ship`: config recommendation = `ship` ve acceptance ship recommendation = `ship`
- `ship_with_ops_note`: hic taraf `no_ship` degil ama en az bir taraf ops note veriyor
- `no_ship`: config veya acceptance tarafindan blocker uretiliyor
