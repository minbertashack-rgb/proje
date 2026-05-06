# Real User E2E Matrix

Bu dokuman acceptance sonrasinda urunun gercek kullanima yakin zincirlerde neyi
olctugunu, neyi bilerek temkinli yorumladigini ve hangi smoke/test ile tekrar
uretilebildigini kisa sekilde toplar.

## Kapsam

- Amac formalite smoke degil; upload sonrasi explanation, concept, retrieval,
  export ve panel zincirlerinde sessiz kiriklari yakalamak.
- Buradaki senaryolar parser gucunu oldugu gibi yazar. Python ve modern Office
  akislari daha guclu; non-Python ve OCR tarafinda parser-benzeri ile heuristik
  siniri korunur.

## Senaryo Matrisi

| ID | Girdi | Akis | Minimum basari | Minimum kalite | Kabul edilemez hata | Durum |
| --- | --- | --- | --- | --- | --- | --- |
| `docx_chunk_explanation_export` | DOCX | upload -> chunks -> anlamadim-v2 -> concepts -> readme-export -> real-export | Upload 201, en az 1 parca, downstream 200 | Aciklama parcaya bagli, concept bos degil, export shape sabit | Upload gecip explanation/export zincirinin bos kalmasi | Otomatik smoke |
| `pptx_summary_concept_anlamadim` | PPTX | upload -> chunks -> calisma-ozeti -> concepts -> detail -> anlamadim-v2 | Slide chunklari ve summary 200 | Summary ana madde cikarir, detail bagli parca dondurur | Slide parse olup summary/concept tarafinin bos kalmasi | Otomatik smoke |
| `xlsx_table_logic_and_analytics` | XLSX | upload -> chunks -> anlamadim-v2 -> excel-modes -> export-readiness | Table chunklari ve analytics 200 | Tablo mantigi gorunur, panel bos degil | Table parse olup aciklamanin duz genel metne donmesi | Otomatik smoke |
| `text_pdf_summary_and_export` | Text PDF | upload -> chunks -> calisma-ozeti -> readme-export | PDF parse ve downstream 200 | Summary ve export okunabilir | PDF parse olup alt akislarin bos kalmasi | Mevcut acceptance + manuel |
| `scanned_pdf_ocr_retrieval` | Image-only/scanned PDF | upload -> OCR fallback -> chunks -> concepts -> ai2 kanitli-cevap | OCR fallback ile parca olusur, retrieval 200 | `visual_ocr` meta ve citation korunur | OCR kullanildigi halde response'un bunu gizlemesi veya sessiz bosluk | Otomatik smoke |
| `ocr_image_direct_upload` | PNG/JPG OCR image | upload | Duzgun kabul veya durust ret | Sahte basari yok, hata yonlendirici | Belirsiz hata ya da sahte `parcalandi` | Otomatik smoke |
| `txt_md_summary_readme` | TXT/MD | upload -> chunks -> calisma-ozeti -> readme-export -> panels-kpi | Heading-aware text chunklari ve aggregate panel 200 | Summary dolu, aggregate cevap ham metin tasimaz | Teknik olarak gecip kullaniciya bos cevap donmesi | Otomatik smoke |
| `python_code_explanation` | Python code | upload -> chunks -> anlamadim-v2 | Function/method/test chunklari ve explanation 200 | `function_purpose`, `flow_summary`, `line_comments`, `block_comments` dolu | Kod chunk'i varken explanation'in anlamsiz kalmasi | Otomatik smoke |
| `non_python_js_safe_explanation` | JavaScript code | upload -> chunks -> anlamadim-v2 | Function/api_call/control_flow sinyalleri korunur | Event -> api -> state akisi gorunur | JS event handler'in Python gibi veya duz metin gibi anlatilmasi | Otomatik smoke |
| `non_python_ps1_safe_explanation` | PowerShell | upload -> chunks -> anlamadim-v2 | Pipeline ve dis cagri sinyali korunur | Heuristik sinir korunur, parser gucu abartilmaz | PowerShell akisinin duz metne donmesi | Smoke script / manuel |
| `concept_surface_detail_chain` | Yapisal dokuman | upload -> concepts -> detail | Surface ve detail 200 | Detail bagli parca dondurur | Surface dolu iken detail'in kopmasi | Otomatik smoke |
| `retrieval_rag_answer_chain` | PDF/DOCX/scanned PDF | upload -> chunks -> ai2 kanitli-cevap | Citation ile cevap 200 | Kanita bagli cevap, citation sayisi tutarli | Citation disi uydurma | Otomatik smoke |
| `export_and_readme_consistency` | DOCX/MD/PDF | upload -> readme-export -> real-export/export-manifest | Export JSON shape sabit | Manifest ve output_meta tutarli | Export hazir gorunup meta/download tarafinin bos kalmasi | Otomatik smoke + acceptance |
| `panel_kpi_aggregate_no_leak` | Mixed docs | upload -> urun yuzeyleri -> analytics/kpi -> panels-kpi | KPI endpointleri 200 | Numeric aggregate, ham icerik sizmaz | Aggregate endpoint'in ham metin veya ic teknik alan donmesi | Otomatik smoke |

## Guclu Alanlar

- Python code explanation zinciri en guclu alan. Upload sonrasi code unit, test
  step ve explanation alanlari birlikte kontrol ediliyor.
- Modern Office akislari (`docx`, `xlsx`, `pptx`) upload sonrasi concept,
  summary ve export zincirine kadar tekrar uretilebilir durumda.
- Panel/KPI tarafi gercek upload edilmis belgelerden sonra aggregate/no-leak
  davranisi ile kontrol ediliyor; yalnizca model fixture'lariyla degil.

## Temkinli Alanlar

- Non-Python code tarafinda yorumlar guvenli ve gorunene sadik olmali; parser
  derinligi Python kadar iddiali degil.
- OCR tarafinda basari, anlamli metin cikarilmasina bagli. Duzgun OCR
  cikaramayan taramalarda sistemin durustce 422 donmesi bekleniyor.
- Duz image upload varsayilan olarak kapali. Bu bir parser eksikligi degil;
  urun/operasyon tercihidir ve smoke matriste ayri hata yuzeyi olarak izlenir.

## Bu Turdaki Net Kazanim

- Gercek upload endpoint'i uzerinden upload -> explanation -> concept ->
  retrieval/export/panel zincirleri tekrar uretilebilir smoke haline getirildi.
- Scanned PDF OCR fallback kullaniminda upload response icindeki `ocr` alani
  artik gercek davranisi yansitiyor; payload shape degismeden sessiz yanlis
  sinyal temizlendi.
