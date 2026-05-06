# Code Explanation Benchmark

Bu dokuman, kod aciklama hattinin "su an geciyor" seviyesinde kalmamasini ve tekrar uretilebilir kalite kontratiyla izlenmesini ozetler.

Makinece calisan kaynak:

- `dokuman/tests/code_explanation_benchmark_data.py`
- `dokuman/tests/code_explanation_benchmark_helpers.py`
- `dokuman/tests/test_special_chunk_explanations.py`

## Resmi Benchmark Kontrati

- Resmi scored golden set: `22` ornek
- Resmi rubric: `7` eksen
- Tum scored case'lerde `anti_hallucination=2` floor'u zorunlu
- Axis minimumlari ve allowlist kurallari merge review gerektirir

## Benchmark Matrisi

| Eksen | Guven tipi | Min skor | Sert floor |
| --- | --- | ---: | --- |
| Python test | parser_backed | 12/14 | accuracy=2, specificity=2, clarity=2, anti_hallucination=2, line_block_alignment=2 |
| Python function | parser_backed | 11/14 | accuracy=2, clarity=2, anti_hallucination=2 |
| Python class/method | parser_backed | 11/14 | accuracy=2, clarity=2, anti_hallucination=2 |
| JavaScript / TypeScript | parser_like_heuristic | 10/14 | clarity=2, anti_hallucination=2 |
| SQL | clause_heuristic | 10/14 | clarity=2, anti_hallucination=2 |
| HTML / CSS | structure_heuristic | 9/14 | anti_hallucination=2 |
| JSON / YAML | key_value_heuristic | 9/14 | anti_hallucination=2 |
| shell / ps1 | command_flow_heuristic | 9/14 | anti_hallucination=2 |

## Rubric

Her scored golden ornek su `7` boyutta `0-2` puan alir:

- `accuracy`
- `specificity`
- `clarity`
- `anti_generic`
- `anti_hallucination`
- `line_block_alignment`
- `concise_readable`

Puanlama kurali:

- eksen bazli minimum toplam skor gecilmeli
- `anti_hallucination` tum eksenlerde `2` olmali
- Python test ekseninde arrange / act / assert ve assertion nedeni daha sert uygulanir
- payload shape, no-leak ve explanation allowlist kontrati bozulmamalidir

## Golden Set Yonetisimi

Yeni case ekleme standardi:

- gercek coverage boslugu kapatmali
- mevcut case'i sadece ad degistirip cogaltmamali
- `good_output`, `bad_output`, `unacceptable_errors` net olmali
- `coverage_tags` tasimali
- eksen minimumlarini anlamsiz sekilde gevsetmemeli

Review gerektiren degisiklikler:

- case sayisinin artmasi veya azalmasi
- coverage tag standardinin degismesi
- axis min skorlarinin degismesi
- allowlist veya anti-hallucination floor kurallarinin degismesi

## Heuristik Sinir

Guclu alan:

- Python test/function/class tarafinda parser-backed meta nedeniyle satir ve blok uyumu daha istikrarli

Temkinli okunacak alan:

- JavaScript / TypeScript, SQL, HTML/CSS, JSON/YAML ve shell yuzeyleri heuristik sinirlidir
- bu alanlarda parser-backed kesinlik varmis gibi davranilmaz
- benchmark gorunmeyen runtime, optimizer, env veya UI sonucu uydurmayi ceza sayar

## Asgari Kabul

- scored case'lerin hicbiri fail etmez
- eksen bazli min skorlar ve floor'lar korunur
- `function_purpose`, `flow_summary`, `block_comments`, `line_comments` regress etmez
- benchmark iyi/kotu cikti ayrimi gercek kalite farki uretmeye devam eder
