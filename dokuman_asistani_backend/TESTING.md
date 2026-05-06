# Test Calistirma

Bu dosya merge kapisi, acceptance akisi ve operasyon notlarini tek yerde toplar. Kisa teslim ozeti [HANDOFF_ONEPAGE.md](HANDOFF_ONEPAGE.md), demo ve release sirasi [DEMO_RELEASE_RUNBOOK.md](DEMO_RELEASE_RUNBOOK.md) icindedir.

## Ozet Komut Matrisi

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\release_preflight.ps1
& $env:DOCVERSE_PYTHON manage.py check
& $env:DOCVERSE_PYTHON .\tools\run_parser_ingestion_smoke.py
python -m py_compile manage.py
python -m py_compile dokuman\views.py dokuman\views_ai2.py dokuman\views_ingestion.py
# Release gate (cross-platform):
python tools/run_release_gate.py
# Quick OCR smoke (optional but useful to validate native OCR):
python tools/ocr_smoke.py
# Install with constraints for deterministic installs:
python -m pip install --upgrade pip
pip install -r requirements-dev.txt -c constraints.txt
```

Minimum merge kapisi:

```powershell
& $env:DOCVERSE_PYTHON -m pytest -q dokuman\tests\test_special_chunk_explanations.py
& $env:DOCVERSE_PYTHON -m pytest -q dokuman\tests\test_multiformat_ingestion.py
& $env:DOCVERSE_PYTHON -m pytest -q dokuman\tests\test_ai2_guardrails.py
& $env:DOCVERSE_PYTHON -m pytest -q dokuman\tests\test_ai2_runtime_tools.py
& $env:DOCVERSE_PYTHON -m pytest -q dokuman\tests\test_ai_eval_contracts.py
```

AI aciklama davranisina dokunulan PR'larda ek kalite kapisi:

```powershell
& $env:DOCVERSE_PYTHON -m pytest -q dokuman\tests\test_anlamadim_quality.py
```

Acceptance:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_acceptance_sequential.ps1 -PythonExe $env:DOCVERSE_PYTHON
```

Tek tek suite kosmak gerekirse:

```powershell
& $env:DOCVERSE_PYTHON -m pytest -q -m suite_a
& $env:DOCVERSE_PYTHON -m pytest -q -m suite_b
& $env:DOCVERSE_PYTHON -m pytest -q -m suite_c
```

## Neden Bu Merge Kapisi?

Bu minimum set, en pahali regressions yuzeyini birlestirir:

- `test_special_chunk_explanations.py`: benchmark/golden set, code explanation kontrati, anti-hallucination floor
- `test_multiformat_ingestion.py`: PDF OCR fallback, legacy Office fallback, metadata tabani
- `test_ai2_guardrails.py`: guardrail, no-leak ve istem siniri
- `test_ai2_runtime_tools.py`: runtime heuristik sinirlari ve aciklama yardimcilari
- `test_ai_eval_contracts.py`: eval payload, shape ve allowlist kontrati
- `test_anlamadim_quality.py`: aciklama kalitesine dogrudan etkisi olan degisikliklerde ek kalite kilidi

Bu set merge oncesi minimumdur. Release ve teslim icin `suite_a`, `suite_b`, `suite_c` de zorunludur.

## Release Gate Ozeti

`release_gate.yml` artik iki ek sinyal tasir:

- `must_pass`: release karari icin resmi zorunlu test
- `acceptance_area`: testin baglandigi acceptance alani

Resmi acceptance alanlari:

- `parsing_ingestion`
- `ocr`
- `explain_anlamadim`
- `retrieval_evidence`
- `auth_api_contract`
- `security_no_leak`
- `notes_history`

Ilk must-pass cekirdek set:

- `test_upload_fields.py`
- `test_ocr_ingestion.py`
- `test_multiformat_ingestion.py`
- `test_views_hardening.py`
- `test_patch2_auth_error_shapes.py`
- `test_patch3_explain_evidence_notes_shapes.py`
- `test_patch6_throttle_shapes.py`
- `test_anlamadim_quality.py`
- `test_rag_quality.py`

`python tools/run_release_gate.py` sonunda artik su artifact'ler uretilir:

- `release_gate_summary.json`
- `release_acceptance_summary.json`
- `release_acceptance_summary.txt`

Kisa acceptance ozeti sunlari gorunur kilar:

- gecen / kalan must-pass testler
- acceptance area bazli durum
- `ship`, `ship_with_ops_note`, `no_ship` onerisi
- skip / fail nedenleri

Karar mantigi:

- `no_ship`: must-pass test fail/skip, acceptance area fail veya `release_checks.py` blocker
- `ship_with_ops_note`: must-pass temiz ama warning / skip notu var
- `ship`: must-pass temiz, acceptance alanlari temiz, blocker ve ops note yok

## Benchmark ve Golden Yonetisimi

- Resmi scored golden set `22` ornektir.
- Rubric `7` eksenlidir.
- `anti_hallucination=2` tum scored case'lerde floor olarak zorunludur.
- `coverage_tags`, case sayisi, axis floor veya allowlist kurallari degisirse review zorunludur.

Yeni golden case kurali:

- gercek coverage boslugu kapatmali
- `good_output`, `bad_output`, `unacceptable_errors` acik olmali
- `coverage_tags` tasimali
- benchmark'i sisirip sinyal kalitesini dusurmemeli

Non-Python siniri:

- JavaScript / TypeScript, SQL, HTML/CSS, JSON/YAML ve shell alanlari parser-backed degil
- bu yuzeylerde benchmark heuristik siniri net gostermeli
- benchmark parser gucu varmis gibi davranmamali

## Acceptance Akisi

`tools/run_acceptance_sequential.ps1` artik daha dayaniklidir:

- her suite'i ayri pytest sureci olarak kosar
- repo kokune ait eski pytest sureclerini temizler
- suite bazli stdout/stderr loglari yazar
- loglari `acceptance_logs/<timestamp>/` altina toplar
- kisa inter-suite bekleme ile ardışik kosu basincini azaltir
- `environment_timeout`, `environment_interruption` ve `deterministic_regression` ayrimini yapar

Onerilen cagrilar:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_acceptance_sequential.ps1 -PythonExe $env:DOCVERSE_PYTHON
powershell -ExecutionPolicy Bypass -File .\tools\run_acceptance_sequential.ps1 -PythonExe $env:DOCVERSE_PYTHON -PerSuiteTimeoutSec 2400
```

Fail siniflandirmasi:

- `deterministic_regression`: pytest exit code ile tekrarlanabilir test kirigi
- `environment_timeout`: suite verilen timeout icinde bitmedi, loga bakilmali
- `environment_interruption`: pytest ozeti tamamlanmadan surec koptu, tek-suite rerun ile teyit edilmeli
- `heuristic_quality_boundary`: benchmark/golden set floor fail'i
- `portability_or_documentation_gap`: script parametresi, env, GGUF veya Tesseract eksigi

Windows oturum timeout'lari gercek test fail'i ile karismasin diye once suite loglarina ve exit sinifina bakilmalidir.

## Portability ve Ortam Notlari

Dogrulanmis ama tasinabilir olmayan noktalar:

- env: `dj310_clean`
- GGUF: repo disi dogrulanmis yol
- Tesseract: sistem kurulumuna bagli
- repo tam pinli production lockfile sunmuyor

Bu nedenle script cagrilarinda sunlar tercih edilmelidir:

```powershell
$env:DOCVERSE_PYTHON = "C:\path\to\python.exe"
$env:DOCVERSE_GGUF_PATH = "D:\models\your-model.gguf"
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

`release_preflight.ps1` ve `start_ai2_server.ps1` once explicit parametreleri, sonra ortam degiskenlerini, sonra Q5 varsayilanini, sonra legacy Q4 fallback yolunu dener.

## Release ve Demo Sirasi

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\release_preflight.ps1
& $env:DOCVERSE_PYTHON manage.py check
& $env:DOCVERSE_PYTHON .\tools\run_parser_ingestion_smoke.py
powershell -ExecutionPolicy Bypass -File .\tools\run_acceptance_sequential.ps1 -PythonExe $env:DOCVERSE_PYTHON
```

AI2 bagimli demo gerekiyorsa:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\start_ai2_server.ps1 -PythonExe $env:DOCVERSE_PYTHON -NThreads 4 -ReadyTimeoutSec 240
powershell -ExecutionPolicy Bypass -File .\tools\watch_ai2_server.ps1
powershell -ExecutionPolicy Bypass -File .\tools\smoke_docverse_e2e.ps1 -Username cemre2 -Password 12345678 -FilePath .\test.docx -BaseUrl http://127.0.0.1:8001
```

## Son No-Leak Kontrolu

Release oncesi son kez su cizgi kontrol edilmelidir:

- urun payload'larinda raw code donmemeli
- raw chunk text ve genis debug meta gereksiz yuzeylere sizmamalidir
- benchmark/eval ic alanlari urun response'larina tasinmamalidir
- explanation payload'lari `function_purpose`, `flow_summary`, `block_comments`, `line_comments` gibi yararli alanlari tutarken kod sizdirmemelidir
