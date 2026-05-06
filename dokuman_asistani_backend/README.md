# Dokuman Asistani Backend

Bu repo teslim ve demo icin stabilize edilmis DocVerse backend hattidir. Ana urun yuzeyleri:

- dokuman yukleme ve parser/ingestion
- OCR ile gorselden metin cikarma
- retrieval / RAG ve kanitli cevap
- `anlamadim-v2` ve concept runtime yuzeyleri
- panel / KPI / analytics endpointleri

## Destek Gercegi

- Tam destek: PDF text-layer, DOCX, XLSX/XLSM, PPTX, TXT/MD/RST, CSV/TSV, gorseller, kod/config dosyalari.
- Kismi ama urunlesmis destek:
  - scanned / image-only PDF -> otomatik OCR fallback
  - legacy `.doc / .xls / .ppt` -> kontrollu red + donusum yonlendirmesi (`.docx / .xlsx / .pptx`)
- Kapsam disi: ODT / ODS / ODP, EPUB, MSG ve diger vendor-spesifik binary formatlar.

## Bilinen Sınırlar ve Dürüstlük Beyanı (Known Limitations)

Proje akademik ve mühendislik dürüstlüğünü korumak adına sınırlarını açıkça beyan eder:
- **Non-Python Diller Heuristik Odaklıdır:** JavaScript/TS, HTML/CSS, SQL, JSON/YAML ve Shell parçaları AST (parser-backed) tabanlı değildir, Regex/Pattern heuristikleri ile çalışır.
- **Derin Semantik Analiz Yoktur:** SQL için optimizasyon/execution planı, YAML için alias/anchor merge sonuçları LLM tarafından kesinleştirilmez. Sadece görünen kod blokları analiz edilir.
- **OCR Kalite Varyansı Gerçektir:** Taranmış PDF ve görsellerdeki çıkarım kalitesi kaynak dosya çözünürlüğüne bağlıdır; sistem zayıf OCR'ı hissederse "abstain" (ret) veya güvenli fallback uygular.
- **Legacy Office Belgeleri:** `.doc` / `.xls` / `.ppt` için bu repoda guvenilir dogrudan parser yoktur; sistem bunlari sessiz bozmak yerine donusum gerektiriyor olarak reddeder.
- Sistemin ana gücü bu sınırları aşmak değil; bu sınırlara yaklaşıldığında **halüsinasyon üretmemek, sızıntı yapmamak ve güvenli bir şekilde geri çekilmektir (abstain/fallback).**

## Olgunluk Seviyeleri (Readiness Gates)

Proje değerlendirmesi 3 aşamalı bir sisteme dayanır (bkz. `FINAL_CLOSURE_SCORECARD.md`):
1. **Demo-Ready:** Temel RAG, OCR ve Anlamadım akışları güvenilir. Çökme yok. Gösterime hazır.
2. **Release-Ready:** Strict no-leak (sızıntısızlık) garanti. Portability (taşınabilirlik) testleri çalışıyor. Acceptance logları deterministik. 
3. **Academic-Ready:** Metodoloji şeffaf, fallback'ler dürüst, benchmark kanıtları tekrarlanabilir, bilinen riskler (yukarıdaki sınırlar) net tanımlı.

## Dogrulanmis Profil ve Portability Notu

- Dogrulanmis repo koku: `C:\Users\cemre\OneDrive\Desktop\tubitak_egitim\dokuman_asistani_backend`
- Dogrulanmis env: `dj310_clean`
- Dogrulanmis Python: `C:\Users\cemre\miniconda3\envs\dj310_clean\python.exe`
- Dogrulanmis GGUF: `C:\Users\cemre\OneDrive\Desktop\ddd\Qwen2.5-7B-Instruct-Q5_K_M.gguf`
- Dogrulanmis Tesseract: `C:\Program Files\Tesseract-OCR\tesseract.exe`

Bu yollar referans profildir; tasinabilir varsayim degildir. Farkli makinede su parametre veya ortam degiskenleri kullanilmalidir:

```powershell
$env:DOCVERSE_PYTHON = "C:\path\to\python.exe"
$env:DOCVERSE_GGUF_PATH = "D:\models\your-model.gguf"
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Scriptler once explicit parametreyi, sonra ortam degiskenlerini, sonra Q5 varsayilanini, sonra legacy Q4 fallback'i dener. Repo halen tam pinli production lockfile sunmuyor; yeniden kurulum iddiasi yerine dogrulanmis calisma profili belgelenmistir.

## Hizli Baslangic

1. Ortami dogrula:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\release_preflight.ps1
```

2. Django API:

```powershell
& $env:DOCVERSE_PYTHON manage.py runserver 8001
```

3. AI2 server:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\start_ai2_server.ps1 -PythonExe $env:DOCVERSE_PYTHON -NThreads 4 -ReadyTimeoutSec 240
```

4. AI2 durum izleme:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\watch_ai2_server.ps1
```

## Minimum Merge Kapisi

Bloklayici minimum kapı su set olmalidir:

- `dokuman/tests/test_special_chunk_explanations.py`
- `dokuman/tests/test_multiformat_ingestion.py`
- `dokuman/tests/test_ai2_guardrails.py`
- `dokuman/tests/test_ai2_runtime_tools.py`
- `dokuman/tests/test_ai_eval_contracts.py`
- Gerekiyorsa AI aciklama kalitesini elle degistiren turlerde `dokuman/tests/test_anlamadim_quality.py`

Bu set minimumdur cunku birlikte su cizgiyi tutar:

- kod aciklama benchmark ve anti-hallucination floor
- multiformat ingestion, OCR fallback ve metadata tabani
- AI2 guardrail ve runtime tool sinirlari
- eval contract ve payload/no-leak kontrati

Bu set yeterlidir cunku her PR'da tum acceptance'i bloklayici yapmak yerine en pahali riskleri tek kapida toplar. `suite_a/b/c` yine release ve teslim oncesi zorunlu kalir.

## Benchmark Yonetisimi

- Resmi scored golden set: `22` ornek
- Resmi rubric: `7` eksen
- `anti_hallucination=2` floor'u tum scored case'lerde zorunlu
- `coverage_tags`, axis floor'lari veya allowlist kurallari degisirse review zorunludur
- Yeni case eklemek icin:
  - tekrar etmeyen bir risk veya coverage boslugu kapatmali
  - `good_output`, `bad_output`, `unacceptable_errors` acik olmalı
  - uygun `coverage_tags` tasimali
  - eksen min skorlarini anlamsiz sekilde gevsetmemeli

## Acceptance ve Release Sirasi

Minimum release sirasi:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\release_preflight.ps1
& $env:DOCVERSE_PYTHON manage.py check
& $env:DOCVERSE_PYTHON .\tools\run_parser_ingestion_smoke.py
powershell -ExecutionPolicy Bypass -File .\tools\run_acceptance_sequential.ps1 -PythonExe $env:DOCVERSE_PYTHON
```

`run_acceptance_sequential.ps1` artik:

- `suite_a -> suite_b -> suite_c` akisini ayri pytest surecleriyle kosar
- repo kokune ait asili pytest sureclerini temizler
- kisa inter-suite bekleme ile ardışik kosuyu daha dengeli hale getirir
- suite-bazli stdout/stderr logu yazar
- timeout, ortam kesintisi ve deterministic regression'i ayirir
- acceptance loglarini `acceptance_logs/` altinda saklar

Demo gerekiyorsa son adim:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\smoke_docverse_e2e.ps1 -Username cemre2 -Password 12345678 -FilePath .\test.docx -BaseUrl http://127.0.0.1:8001
```

## Son Kalite Notlari

- no-leak cizgisi urun payload'larinda raw code, raw chunk text ve benchmark internal alanlarini sizdirmemelidir
- benchmark formalite degil; iyi/kotu cikti kontrati ve anti-hallucination floor ile merge kalitesi olcmelidir
- non-Python taraf parser-backed degil; docs ve benchmark bu siniri heuristik olarak acik soylemelidir

## Referans Dokumanlar

- [TESTING.md](TESTING.md)
- [DEMO_RELEASE_RUNBOOK.md](DEMO_RELEASE_RUNBOOK.md)
- [HANDOFF_ONEPAGE.md](HANDOFF_ONEPAGE.md)
- [HANDOFF_PRODUCT_PHASE.md](HANDOFF_PRODUCT_PHASE.md)
- [CODE_EXPLANATION_BENCHMARK.md](CODE_EXPLANATION_BENCHMARK.md)
- [CODE_EXPLANATION_GOLDENS.md](CODE_EXPLANATION_GOLDENS.md)
