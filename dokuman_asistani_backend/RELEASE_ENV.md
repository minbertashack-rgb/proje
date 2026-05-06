# Release Environment

Bu dosya release readiness icin kritik environment ve config sinyallerini kisa ve zorunlu sekilde toplar.

## Config Gate Siniflari

`ok`

- release config acisindan blocker yok

`warning`

- release kosulabilir ama operasyon notu dusulmelidir
- final karar genelde `ship_with_ops_note` cizgisine gider

`blocker`

- release adayi `no_ship` sayilir

`tools/release_checks.py` su artifact'leri uretir:

- `release_checks_report.json`
- `release_checks_summary.txt`

## Kritik Ayarlar

Zorunlu:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=0`
- `DOCVERSE_UPLOAD_MIN_BYTES`
- `DOCVERSE_UPLOAD_MAX_BYTES`
- `DOCVERSE_THROTTLE_TOKEN_OBTAIN_RATE`
- `DOCVERSE_THROTTLE_TOKEN_REFRESH_RATE`
- `DOCVERSE_THROTTLE_UPLOAD_RATE`
- `DOCVERSE_THROTTLE_ANLAMADIM_RATE`
- `DOCVERSE_THROTTLE_KANITLI_CEVAP_RATE`
- `DOCVERSE_THROTTLE_NOTES_WRITE_RATE`

OCR / ingestion:

- `TESSERACT_CMD`
- `OCR_LANG`

AI runtime:

- `AI2_TABAN_ADRESI` veya `AI2_BASE_URL`
- `AI2_MODEL_ADI` veya `AI2_MODEL`
- `AI2_ZAMAN_ASIMI` veya `AI2_TIMEOUT`
- opsiyonel local fallback icin `DOCVERSE_GGUF_PATH`

## Gate Kurallari

Blocker ureten tipik durumlar:

- `DEBUG=True`
- varsayilan / eksik `DJANGO_SECRET_KEY`
- upload min/max byte limitleri gecersiz
- throttle rate ayarlari eksik veya bozuk
- AI2 timeout <= 0 veya model alias bos

Warning ureten tipik durumlar:

- `TESSERACT_CMD` eksik
- AI2 base URL explicit degil ve implicit localhost varsayiminda
- yerel model etkin ama GGUF yolu bulunamiyor
- `CORS_ALLOW_ALL_ORIGINS=True`

## Karar Matrisi

Config recommendation ile acceptance ship recommendation birlikte okunur:

- taraflardan biri `no_ship` ise final karar `no_ship`
- hic `no_ship` yok ama en az biri `ship_with_ops_note` ise final karar `ship_with_ops_note`
- iki taraf da `ship` ise final karar `ship`

## Hızlı Akis

```powershell
& .\.conda\python.exe .\tools\release_checks.py
& .\.conda\python.exe .\tools\benchmark_audit.py
& .\.conda\python.exe .\tools\run_release_gate.py
```
