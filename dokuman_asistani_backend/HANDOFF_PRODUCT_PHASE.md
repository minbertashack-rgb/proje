# Urun Fazina Gecis Ozeti

## Calisma Profili

- Django API portu: `8001`
- AI2 / llama_cpp server portu: `8002`
- Model alias: `qwen-docverse`
- Ana GGUF: `C:\Users\cemre\OneDrive\Desktop\ddd\Qwen2.5-7B-Instruct-Q5_K_M.gguf`
- `AI2_TEST_MODU`: test ve normal token butceleri ayrilmis durumda
- Operasyon ve probe notlari: `TESTING.md`

## AI2 Durumu

- `dokuman.ai2.llm.chat()` public API korunuyor.
- AI2 readiness artik `/v1/models` probe ile kontrol ediliyor.
- `tools/run_anlamadim_live_batch.py` canli kalite ve latency olcumu icin standart aractir.
- `tools/ai2_runtime.py` runtime readiness, startup ve `process_exited_early` tanisi toplar.

## Parser / Fallback / Validators

- `anlamadim-v2` icin parser + merge + fallback zinciri sertlestirildi.
- Yari JSON, markdown karisimi ve tip kaymasi icin `dokuman/ai2/validators.py` salvage hatti var.
- `very_simple` ve kisa tablo/etiket fallback'leri parcaya daha bagli hale getirildi.
- `heading_parser` yalanci heading oranini azaltacak sekilde guclendirildi.
- `ingestion` kisa ama anlamli icerigi daha iyi korur; sahte `parcalandi` korumasi duruyor.

## Test Seviyesi

- Guncel durum: `64 passed`
- `manage.py check`: temiz
- Canli batch raporlari:
  - tam referans: `tools/anlamadim_live_batch_report_internal_v3.json`
  - standart kisa dogrulama: `tools/anlamadim_live_batch_report_internal_v4.json`

## Sonraki Moduller Icin Onerilen Oncelik

1. `RAG`
   Amaç: retrieval kalitesi, citation guvencesi, latency/kalite dengesi
2. `OCR`
   Amaç: dusuk kaliteli goruntu/PDF senaryolari, OCR chunk kalitesi
3. `notlar / portal notlar`
   Amaç: urun akislarinda not alma, bagli belge/adres deneyimi
4. `cheatsheet / export`
   Amaç: derlenmis ozet ve cikti formatlarinin urunlestirilmesi
5. `quiz / boss / anlat-kontrol`
   Amaç: pedagojik oyunlastirma ve ogrenme geri bildirimi

## Teknik Borclar

- AI2 latency varyansi yuksek; startup maliyeti model load/repack kaynakli.
- AI2 bazen strict JSON yerine yari-serbest cikti veriyor; salvage var ama tam cozulmedi.
- Batch ve benchmark artefaktlari repo root yerine zamanla tek bir `reports/` klasorunde toplanmali.
- `views.py` halen buyuk; urun fazinda modulerlestirme dusunulebilir, ama su an davranis korunuyor.
- Runtime parametre tuning (`n_ctx`, `n_threads`, `n_gpu_layers`) sistem kapasitesine gore ayri benchmark ile sabitlenmeli.
