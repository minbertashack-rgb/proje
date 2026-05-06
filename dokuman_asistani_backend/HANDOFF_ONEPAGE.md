# Handoff One Pager

Bu proje DocVerse backend'idir. Dokuman yukler, parser/ingestion ile parcalar, OCR cikarir, `anlamadim-v2` ve concept runtime yuzeylerini sunar, RAG ile kanitli cevap uretir ve panel/KPI/analytics endpointleri verir.

## Destek Durumu

- Tam destek: PDF text-layer, DOCX, XLSX/XLSM, PPTX, TXT/MD/RST, CSV/TSV, gorseller, kod/config dosyalari
- Kismi ama urunlesmis destek:
  - scanned / image-only PDF icin otomatik OCR fallback
  - legacy `.doc / .xls / .ppt` icin kismi text extraction + durust meta
- Kapsam disi: ODT / ODS / ODP, EPUB, MSG ve diger ozel binary formatlar

**Önemli Bilinen Sınırlar:** Non-Python diller (SQL, YAML, JS, Shell) için parser bulunmaz, heuristik çalışır. OCR kalitesi çözünürlüğe bağlıdır. Sistemin esas gücü bu sınırları aşmak değil, aşılamayan noktada **halüsinasyon yapmadan geri çekilmesidir (abstain).** Tüm hazırlık ve kapanış durumları `FINAL_CLOSURE_SCORECARD.md` içinde belgelenmiştir.

## Minimum Calisma Ortami

- Dogrulanmis env: `dj310_clean`
- Python: `DOCVERSE_PYTHON` ile verilmeli
- GGUF: repo disi olabilir, `DOCVERSE_GGUF_PATH` veya `-ModelPath` ile verilmeli
- Tesseract: sistem kurulu olmali, `TESSERACT_CMD` veya `-TesseractPath` ile verilmeli

## Baslatma

```powershell
$env:DOCVERSE_PYTHON = "C:\path\to\python.exe"
$env:DOCVERSE_GGUF_PATH = "D:\models\your-model.gguf"
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"

powershell -ExecutionPolicy Bypass -File .\tools\release_preflight.ps1
& $env:DOCVERSE_PYTHON manage.py runserver 8001
powershell -ExecutionPolicy Bypass -File .\tools\start_ai2_server.ps1 -PythonExe $env:DOCVERSE_PYTHON -NThreads 4 -ReadyTimeoutSec 240
```

## Minimum Merge ve Acceptance

Minimum merge kapisi:

- `test_special_chunk_explanations.py`
- `test_multiformat_ingestion.py`
- `test_ai2_guardrails.py`
- `test_ai2_runtime_tools.py`
- `test_ai_eval_contracts.py`

AI aciklama davranisina dokunulduysa ek:

- `test_anlamadim_quality.py`

Release acceptance:

```powershell
& $env:DOCVERSE_PYTHON manage.py check
& $env:DOCVERSE_PYTHON .\tools\run_parser_ingestion_smoke.py
powershell -ExecutionPolicy Bypass -File .\tools\run_acceptance_sequential.ps1 -PythonExe $env:DOCVERSE_PYTHON
```

## Demo Smoke

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\smoke_docverse_e2e.ps1 -Username cemre2 -Password 12345678 -FilePath .\test.docx -BaseUrl http://127.0.0.1:8001
```

## Ilk Bakilacak Yerler

- `tools\release_preflight.ps1`
- `acceptance_logs\`
- `ai2_server_runtime.err.log`
- `ai2_server_runtime.out.log`
- GGUF yolu ve `8002` portu
- Django `8001` portu

## Teslim Paketine Alma

Alma:

- kaynak kod
- `tools/` scriptleri
- `FINAL_CLOSURE_SCORECARD.md` (Kapanış Puan Kartı ve Kanıtlar)
- `README.md`
- `TESTING.md`
- `DEMO_RELEASE_RUNBOOK.md`

Disla:

- `__pycache__/`
- `.pytest_cache/`
- `chroma_db/`
- `media/`
- `db.sqlite3`
- `acceptance_logs/`
- probe, benchmark ve gecici payload artefaktlari

## Referanslar

- [README.md](README.md)
- [TESTING.md](TESTING.md)
- [DEMO_RELEASE_RUNBOOK.md](DEMO_RELEASE_RUNBOOK.md)
