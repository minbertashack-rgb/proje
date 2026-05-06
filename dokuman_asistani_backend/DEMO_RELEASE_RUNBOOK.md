# Demo ve Release Runbook

Bu dokuman final demo, acceptance ve teslim oncesi en guvenli calisma sirasini toplar.

## Destek Gercegi

- Tam destek: PDF text-layer, DOCX, XLSX/XLSM, PPTX, TXT/MD/RST, CSV/TSV, gorseller ve kod/config dosyalari
- Kismi destek:
  - scanned / image-only PDF -> OCR fallback
  - legacy `.doc / .xls / .ppt` -> kismi text extraction, yapisal sadakat sinirli
- Kapsam disi: ODT / ODS / ODP, EPUB, MSG ve diger ozel binary formatlar

> **Önemli Not (Academic/Engineering Readiness):** Projenin Non-Python heuristik sınırları (SQL, JS, YAML) ve OCR kalite varyansları birer hata değil, donanımsal/sistemsel gerçektir. Proje bu durumlarda halüsinasyon uydurmaz, kısmi çıkarım veya ret (abstain) uygular. 

## Demo Oncesi Kisa Checklist

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\release_preflight.ps1
& $env:DOCVERSE_PYTHON .\tools\release_checks.py
& $env:DOCVERSE_PYTHON manage.py check
& $env:DOCVERSE_PYTHON .\tools\run_parser_ingestion_smoke.py
powershell -ExecutionPolicy Bypass -File .\tools\run_acceptance_sequential.ps1 -PythonExe $env:DOCVERSE_PYTHON
```

AI2 bagimli demo yapilacaksa:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\start_ai2_server.ps1 -PythonExe $env:DOCVERSE_PYTHON -NThreads 4 -ReadyTimeoutSec 240
powershell -ExecutionPolicy Bypass -File .\tools\watch_ai2_server.ps1
```

Son E2E smoke:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\smoke_docverse_e2e.ps1 -Username cemre2 -Password 12345678 -FilePath .\test.docx -BaseUrl http://127.0.0.1:8001
```

Release smoke probelari gerekiyorsa:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\smoke_docverse_e2e.ps1 `
  -Username cemre2 `
  -Password 12345678 `
  -FilePath .\test.docx `
  -BaseUrl http://127.0.0.1:8001 `
  -ProbeEvidence `
  -ProbeNotes
```

## Demo Sirasi

1. Dokuman yukleme
2. Parcalama / baslik / icerik cikarimi
3. OCR ile gorselden metin cikarimi
4. `anlamadim-v2` / concept runtime
5. Retrieval / kanitli cevap
6. Panel / KPI / analytics

## Merge ve Release Kapisi

**Minimum Merge Kapısı (Hızlı PR Kontrolü):**

- `test_special_chunk_explanations.py`
- `test_multiformat_ingestion.py`
- `test_ai2_guardrails.py`
- `test_ai2_runtime_tools.py`
- `test_ai_eval_contracts.py`
- AI aciklama davranisina dokunulduysa `test_anlamadim_quality.py`

**Release Kapısı (Scorecard Evidence):**
Release kararı öncesi `FINAL_CLOSURE_SCORECARD.md` içindeki kanıtlar toplanmalıdır.

- minimum merge kapisi gecer
- `release_checks.py` sonucu `no_ship` degil
- legacy acceptance gerekiyorsa `suite_a`, `suite_b`, `suite_c`
- hizli release shard kosusu temiz:
  - `upload_ingestion_ocr`
  - `explain_evidence_ai`
  - `api_security_notes`
- demo gerekiyorsa AI2 smoke temiz
- **Kanıtlar:** `acceptance_logs/` dizininde ilgili artifactler üretilmiş olmalıdır.

Release shard listeleme:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_acceptance_sequential.ps1 -Mode release_shards -ListOnly
```

Release shard kosusu:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_acceptance_sequential.ps1 -Mode release_shards -PythonExe $env:DOCVERSE_PYTHON
```

## Acceptance Akisi Neden Ayrik?

`tools/run_acceptance_sequential.ps1` artik:

- suite'leri ayri pytest surecleriyle kosar
- kisa inter-suite bekleme uygular
- timeout, ortam kesintisi ve deterministic fail'i ayirir
- stdout/stderr loglarini `acceptance_logs/` altina toplar
- Windows oturum timeout'unu gercek regression ile karistirmamaya yardim eder

Bu nedenle tek script uzerinden calismasi tercih edilir; ama maskeleme yapmaz, timeout olan suite yine fail sayilir.

`legacy_suites` modu mevcut `suite_a/b/c` davranisini korur.
`release_shards` modu ise dosya-listesi tabanli hizli release acceptance kosusudur.

## Portability ve Teslim Notlari

- dogrulanmis env: `dj310_clean`
- GGUF repo disi olabilir; `-ModelPath` veya `DOCVERSE_GGUF_PATH` verilmelidir
- Varsayilan yerel model artik `Qwen2.5-7B-Instruct-Q5_K_M.gguf` olarak beklenir; eski Q4 yolu yalniz legacy fallback olarak korunur
- Tesseract sistem kurulumu gerektirir; `-TesseractPath` veya `TESSERACT_CMD` verilmelidir
- repo tam pinli production lockfile sunmaz; yeniden kurulum iddiasi yerine dogrulanmis profil + runbook vardir

Tasima oncesi tercih edilen ortam degiskenleri:

```powershell
$env:DOCVERSE_PYTHON = "C:\path\to\python.exe"
$env:DOCVERSE_GGUF_PATH = "D:\models\your-model.gguf"
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Release readiness config checklist:

- `DJANGO_DEBUG=0`
- `DJANGO_SECRET_KEY` explicit verilmeli
- upload byte limitleri gecersiz olmamali
- throttle rate ayarlari dolu olmali
- `TESSERACT_CMD` varsa OCR acceptance daha guvenli okunur
- `AI2_TABAN_ADRESI` / `AI2_MODEL_ADI` / `AI2_ZAMAN_ASIMI` explicit verilirse ops note azalir
- Q5_K_M, Q4'e gore daha gec yuklenebilecegi icin AI2 startup tarafinda `-ReadyTimeoutSec 240` varsayimi kullanilir; request timeout zinciri degistirilmemistir

## Teslim Paketine Girmemesi Gerekenler

- `__pycache__/`
- `.pytest_cache/`
- `chroma_db/`
- `media/`
- `db.sqlite3`
- `ai2_*runtime*.log`
- `*.pid`
- `*_probe*.json`
- `*_probe*.txt`
- `anlamadim_benchmark_*.json`
- `anlamadim_benchmark_*.txt`
- `acceptance_logs/`
- gecici payload ve auth dump dosyalari

## Teslim Karari

- `demo icin hazir`: temel smoke temiz, gosteri akisi kirik degil
- `teslime hazir`: `release_checks.py` = `ship`, acceptance ship recommendation = `ship`, release shard temiz, release smoke temiz
- `kucuk operasyonel not var`: hicbir taraf `no_ship` degil ama config veya acceptance ozetinde `ship_with_ops_note` var
- `hazir degil`: config veya acceptance tarafindan `no_ship` uretiliyor
