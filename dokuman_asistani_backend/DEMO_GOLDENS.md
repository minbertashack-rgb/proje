# AI Demo Goldens

Bu not, mevcut AI yuzeylerini yeni feature eklemeden gostermek icin tekrar uretilebilir demo akislari toplar.
Amac, "girdi -> beklenen kaliteli cikti" cercevesini kisa ve net sekilde gostermektir.

Kod yorumlama odakli ayrik golden kontratlari icin:
- `CODE_EXPLANATION_GOLDENS.md`

## Kullanim Ilkesi

- Yeni endpoint yok.
- Payload shape beklentisi degistirilmiyor.
- Demo sirasinda ham icerik sizmasi beklenmez; metrik ve analytics tarafinda agregat alanlara bakilir.
- Mümkün oldugunca repodaki mevcut dosyalar kullanilir:
  - `test.docx`
  - `test_ingest.pptx`
  - `ocr_test.png`
  - `test_ingest.docx`

## Golden Senaryolar

### 1. DOCX Yukleme ve Parca Cikarimi

- Neden degerli:
  Heading parser, ingestion quality, parca sozlesmesi ve temel upload akisini tek seferde gosterir.
- Input:
  `test.docx` veya `test_ingest.docx`
- Endpoint:
  `POST /api/dokuman-asistani/dokumanlar/yukle/`
  Sonra `GET /api/dokuman-asistani/dokumanlar/{doc_id}/parcalar/`
- Beklenen ana alanlar:
  Upload response icin `id`, `doc_id`, `durum`, `parca_sayisi`
  Parcalar response icin `doc_id`, `parca_sayisi`, `parcalar`
- Iyi cikti nasil gorunur:
  `durum=parcalandi`
  `parca_sayisi >= 1`
  Parcalarda stabil `id`, `adres`, `metin`, `meta`
  Kisa ama gercek icerik kaybolmaz; sadece baslik-only veya imza/meta benzeri satirlar baskilanir
- Kotu cikti nasil gorunur:
  Upload basarili gorunup `parca_sayisi=0`
  Adreslerin bos ya da tekrarli gelmesi
  Kisa ama gercek bolumlerin tamamen kaybolmasi
- Demo kalite sinyalleri:
  `durum`
  `parca_sayisi`
  `parcalar[].adres`
  `parcalar[].meta.baslik`
  `parcalar[].meta.quality_score`
- Sertlestirme faydasi:
  Kisa ama gercek icerigin tutuldugu, sahte basarinin geri donmedigi net gorulur.

### 2. OCR Gorsel Yukleme ve Guvenli Parca Uretimi

- Neden degerli:
  OCR cikisinin hem parca olusturdugunu hem de zayif OCR durumunda guvenli davrandigini gosterir.
- Input:
  `ocr_test.png`
  Ek negatif varyant: dusuk metin yogunluklu veya gurultulu OCR benzeri kisa gorsel
- Endpoint:
  Yukleme icin `POST /api/dokuman-asistani/dokumanlar/yukle/`
  Parca listeleme icin `GET /api/dokuman-asistani/dokumanlar/{doc_id}/parcalar/`
- Beklenen ana alanlar:
  `durum`, `parca_sayisi`
  OCR parcasi metasi icin `path`, `chunk_index`, `ocr`, `quality_score`, `ocr_quality_score`, `difficulty_score`
- Iyi cikti nasil gorunur:
  OCR parcalari `ocr:1`, `ocr:2` gibi adresli gelir
  `meta.ocr = true`
  Kisa ama anlamli OCR metin tamamen oldurulmez
  Düşük kaliteli OCR'da zayiflik sinyali vardir ama sahte "parcalandi" yazilmaz
- Kotu cikti nasil gorunur:
  OCR basarisizken `durum=parcalandi`
  `path`/`chunk_index` olmayan parcilar
  OCR sonucu tablo/kod/bolum gibi yanlis turlenmis cikti
- Demo kalite sinyalleri:
  `parcalar[].tur`
  `parcalar[].adres`
  `parcalar[].meta.ocr_quality_score`
  `parcalar[].meta.quality_score`
  `parcalar[].meta.chunk_kind`
- Sertlestirme faydasi:
  OCR sonrasi sahte basari riskinin kapandigi ve guvenli quality gating gorunur olur.

### 3. Anlamadim-v2 / Concept Runtime Kalitesi

- Neden degerli:
  Mevcut AI yuzeyinin "parcayi acikla" kalitesini ve debug okunabilirligini tek response icinde gosterir.
- Input:
  DOCX/PDF ingestion sonrasi anlamli bir parca
- Endpoint:
  `POST /api/dokuman-asistani/parcalar/{parca_id}/anlamadim-v2/`
- Beklenen ana alanlar:
  `one_liner`, `very_simple`, `glossary`, `steps`, `examples`, `trap`, `mini_quiz`, `dokumanda_yok`
  Opsiyonel debug icin `debug_ai2`
- Iyi cikti nasil gorunur:
  `one_liner` tek cumlede parcaya bagli ozet verir
  `glossary`, `steps`, `examples` bos donmez
  `mini_quiz` 3 adet kisa soru-cevap getirir
  `dokumanda_yok = false`
- Kotu cikti nasil gorunur:
  Genel-gecer ama parcaya bagli olmayan aciklama
  Bos `steps` veya tek satirlik anlamsiz `glossary`
  `dokumanda_yok` yanlis pozitif
- `one_liner` nasil okunur:
  Parcanin en hizli demo ozeti; kaliteli oldugunda parcadaki asli kavrami dogru isimle tekrar eder
- `fallback_nedeni` nasil okunur:
  `debug_ai2.fallback_nedeni` varsa model cikisi dogrudan yetmemis, sistem guvenli merge/fallback yapmis demektir
  Ornek: `ai2_short_output`
- `debug_ai2` nasil okunur:
  Demo icin kalite lensidir; prompt kisaltma, merge ve parse durumunu gosterir
  Ozellikle `merge_gerekli_miydi`, `json_bulundu_mu`, `parse_basarili_mi`, `merge_ile_tamamlanan_alanlar`
- Demo kalite sinyalleri:
  `one_liner`
  `dokumanda_yok`
  `debug_ai2.fallback_nedeni`
  `debug_ai2.merge_gerekli_miydi`
  `debug_ai2.parca_sinifi`
- Sertlestirme faydasi:
  Response shape korunurken kalite tamamlama katmaninin gercek faydasi görünür olur.

### 4. Concept Surface ve Fusion

- Neden degerli:
  Dokumandan cikan kavramlarin weak-only gurultuden arindirilmis ve sade payload ile geldigi gosterilir.
- Input:
  JWT / Refresh Token gibi tekrar eden iki teknik kavram iceren dokuman
  Negatif varyant: weak OCR benzeri parcalarda gecen sahte token
- Endpoint:
  `GET /api/dokuman-asistani/dokumanlar/{doc_id}/concepts/`
  `GET /api/dokuman-asistani/dokumanlar/{doc_id}/concepts/detail/?kavram=JWT`
  `POST /api/dokuman-asistani/dokumanlar/{doc_id}/concepts/fusion/`
- Beklenen ana alanlar:
  Surface icin `dokuman_id`, `toplam_kavram`, `kavramlar`
  Detail icin `dokuman_id`, `kavram`, `kisa_tanim`, `bagli_parca_idleri`, `ornek_gecis_sayisi`
  Fusion icin `dokuman_id`, `kavram_a`, `kavram_b`, `ortak_yonler`, `farklar`, `birlikte_kullanim_ornegi`, `mini_soru`
- Iyi cikti nasil gorunur:
  Gercek kavramlar gorunur
  Weak-only tekrar eden gurultu kavramlari gorunmez
  Fusion sade, kisa ve karsilastirilabilir gelir
- Kotu cikti nasil gorunur:
  OCR gurultusunden uremis sahte kavramlar surface'e cikar
  Fusion ham parca metnini veya sizdirici tanimlari tekrarlar
- Demo kalite sinyalleri:
  `toplam_kavram`
  `kavramlar[].kavram`
  `kavramlar[].kaynak_parca_idleri`
  `detail.ornek_gecis_sayisi`
  `fusion.ortak_yonler`
- Sertlestirme faydasi:
  Weak-only kavram baskilamanin pratik etkisi dogrudan gorunur.

### 5. Retrieval / Kanitli Cevap

- Neden degerli:
  Retrieval, evidence selection ve answer alignment zincirini tek demoda gosterir.
- Input:
  RAG ile ilgili 2-3 parca iceren dokuman
  Semantik veya lexical olarak ayri iki aday parca
- Endpoint:
  `POST /api/dokuman-asistani/dokumanlar/{doc_id}/rag-ara/`
  `POST /api/dokuman-asistani/dokumanlar/{doc_id}/sor/`
  `POST /api/dokuman-asistani/ai2/kanitli-cevap/`
- Beklenen ana alanlar:
  RAG arama icin `count`, `sonuclar`, `retrieval_ozeti`
  Kanitli cevap icin `kanitlar`, `kullanilan_kanit_sayisi`, `kullanilan_parca_idleri`, `kullanilan_kanit_idleri`, `kullanilan_adresler`, `kaynak_guveni`, `retrieval_ozeti`
  AI2 kanitli cevap icin ek olarak `supported`, `citations`, `answer`
- Iyi cikti nasil gorunur:
  `kullanilan_hit` ile secilen kanit sayisi uyumludur
  `citations` ve `kullanilan_parca_idleri` ayni kaniti isaret eder
  Zayif kanitta `supported=false` veya `kaynak_guveni=dusuk` gibi temkinli davranis vardir
- Kotu cikti nasil gorunur:
  Cevap baska parcaya dayanirken citation farkli parca gostermesi
  `retrieval_kaynagi_ozeti` ile gercek hit tipi uyumsuzlugu
  Dusuk kanitta asiri ozguvenli cevap
- `retrieval_ozeti` demo degeri:
  Arka plandaki retrieval kalitesini sahne arkasindan gorunur yapar
  `toplam_hit`, `kullanilan_hit`, `dokuman_filtresi_var_mi`, `auto_index_denendi_mi`, `rerank_uygulandi_mi`, `zayif_kaynak_hit_sayisi`
- `retrieval_kaynagi` demo degeri:
  Sonucun semantik mi, lexical mi, request evidence mi oldugunu netlestirir
  Karma senaryolarda dengeli secimi gostermek icin kritiktir
- Demo kalite sinyalleri:
  `retrieval_ozeti.kullanilan_hit`
  `retrieval_ozeti.retrieval_kaynagi_ozeti`
  `retrieval_ozeti.rerank_uygulandi_mi`
  `retrieval_ozeti.zayif_kaynak_hit_sayisi`
  `kullanilan_kanit_idleri`
  `citations`
- Sertlestirme faydasi:
  Evidence orchestrator, abstain ve alignment iyilestirmelerinin etkisi en net bu senaryoda gorulur.

### 6. PPTX Ingestion Determinism

- Neden degerli:
  Son sertlestirmelerin gorunur etkisini tek bir demo ile kanitlar.
- Input:
  `test_ingest.pptx`
- Endpoint:
  `POST /api/dokuman-asistani/dokumanlar/yukle/`
  Sonra `GET /api/dokuman-asistani/dokumanlar/{doc_id}/parcalar/`
- Beklenen ana alanlar:
  `parcalar[].adres`
  `parcalar[].meta.chunk_kind`
  `parcalar[].meta.slide`
  `parcalar[].meta.slide_title`
- Iyi cikti nasil gorunur:
  `pptx:slide:1`, `pptx:slide:2`, ... gibi numerik ve stabil sira
  Placeholder title gerçek baslik sayilmaz
  Bullet-only slide'da ilk anlamli satir kontrollu baslik olabilir
  Mixed-content slide'da title ve bullets ayrik kalir
- Kotu cikti nasil gorunur:
  `slide10` once gelir
  "Click to add title" gibi placeholder baslik olarak surface'e cikar
  Baslik metni bullet grubuna tekrarla sizar
- Demo kalite sinyalleri:
  `parcalar[].adres`
  `parcalar[].meta.chunk_kind`
  `parcalar[].meta.slide_title`
- Sertlestirme faydasi:
  PPTX title fallback determinism ve numerik slide siralamasinin somut etkisini gosterir.

### 7. Dashboard / KPI / Analytics Gorunurlugu

- Neden degerli:
  AI kalitesinin sadece cevaba degil, guvenli ve izlenebilir urun metriklerine de yansidigini gosterir.
- Input:
  Not, portal not, feedback ve AI uretim olaylari olan kullanici
- Endpoint:
  `GET /api/dokuman-asistani/dashboard/summary/`
  `GET /api/dokuman-asistani/dashboard/summary/v2/`
  `GET /api/dokuman-asistani/analytics/confusion-hotspots/`
  `GET /api/dokuman-asistani/analytics/kpi/`
- Beklenen ana alanlar:
  `toplam_not_sayisi`, `toplam_portal_not_sayisi`, `toplam_feedback`
  `gecerli_feedback_orani`, `dusuk_fayda_orani`, `yuksek_confusion_parca_sayisi`
  `feedback_trust_ratio`, `net_usefulness_score`, `cheatsheet_yield`
- Iyi cikti nasil gorunur:
  Agregat ve sade payload
  Ham not/portal not/feedback metni response'a girmez
  KPI alanlari stabil ve okunur kalir
- Kotu cikti nasil gorunur:
  Note, snippet veya serbest metin sizmasi
  Endpoint shape'inin panel ile analytics arasinda oynaklasmasi
- Demo kalite sinyalleri:
  `set(response.keys())` stabilitesi
  `yuksek_confusion_parca_sayisi`
  `feedback_trust_ratio`
  `net_usefulness_score`
- Sertlestirme faydasi:
  No-leak cizgisinin sadece cevapta degil analytics ve panel yuzeylerinde de korundugu görünür.

## Demo Sirasi Onerisi

1. DOCX upload + parca listesi
2. OCR upload + OCR parca metasi
3. `anlamadim-v2`
4. `concepts` + `concepts/fusion`
5. `rag-ara`
6. `sor` veya `ai2/kanitli-cevap`
7. `dashboard/summary/v2`
8. Vakit varsa PPTX upload ile determinism finali

## Kisa Smoke Onerileri

- Uctan uca upload smoke:
  `powershell -ExecutionPolicy Bypass -File .\\tools\\smoke_docverse_e2e.ps1 -Username <user> -Password <pass> -FilePath .\\test.docx -BaseUrl http://127.0.0.1:8001`
- Hedefli acceptance dostu test gruplari:
  - `dokuman/tests/test_upload_fields.py`
  - `dokuman/tests/test_multiformat_ingestion.py`
  - `dokuman/tests/test_ocr_ingestion.py`
  - `dokuman/tests/test_anlamadim_quality.py`
  - `dokuman/tests/test_concept_runtime.py`
  - `dokuman/tests/test_concept_fusion.py`
  - `dokuman/tests/test_rag_quality.py`
  - `dokuman/tests/test_panels_api.py`

## Kalan Kucuk Riskler

- PPTX fallback halen heuristik; cok duzensiz slide deck'lerde "ilk anlamli satir" secimi sunum uretecisine bagli olabilir.
- Dusuk kaliteli OCR kaynakli gercek ama cok seyrek kavramlar, weak-only baskilama nedeniyle concept surface'e cikmayabilir.
- Demo kalitesi, canli ortamda kullanilan model ve flag setine bagli olarak anlatim tonunda degisebilir; bu rehber shape ve kalite sinyaline odaklanir, tam metin birebirligi vaat etmez.
