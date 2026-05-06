# Code Explanation Goldens

Bu dosya benchmark'ta resmi sayilan golden ornekleri ve iyi/kotu cikti kontratini toplar.

Makinece calisan kaynak:

- `dokuman/tests/code_explanation_benchmark_data.py`

Ana benchmark kurallari:

- [CODE_EXPLANATION_BENCHMARK.md](CODE_EXPLANATION_BENCHMARK.md)

## Resmi Scored Goldens

Python:

- `python_drf_api_test`
- `python_mock_monkeypatch_test`
- `python_helper_assert_chain`
- `python_transform_function`
- `python_nested_loop_function`
- `python_stateful_class`
- `python_state_mutation_method`

JavaScript / TypeScript:

- `js_event_handler`
- `js_api_state_change`
- `js_nested_callback_handler`

SQL:

- `sql_select_join_filter`
- `sql_update_filter`
- `sql_cte_rank_filter`

HTML / CSS:

- `html_markup_block`
- `html_markup_script_style_split`
- `css_style_rule`

JSON / YAML:

- `yaml_config_section`
- `yaml_anchor_alias_section`
- `json_config_entry`
- `json_feature_flags_section`

Shell:

- `powershell_external_call`
- `shell_pipeline_external_call`

## Iyi Cikti Kontrati

- gorunen satira ve bloka bagli kalir
- Python testte hazirlik, yetki, payload, endpoint, assertion ve final state zinciri ayri gorunur
- function/class/method aciklamasinda input, state, donusum, branch ve return etkisi ayrilir
- heuristik alanlarda parser gucu varmis gibi davranmaz
- `function_purpose`, `flow_summary`, `block_comments`, `line_comments` tamamlayici rol tasir

## Kotu Cikti Kontrati

- genel fiiller nesne ve amac baglamadan baskin olur
- `line_comments` veya `block_comments` kaybolur
- `function_purpose` ve `flow_summary` satirdan kopuk kalir
- kodda gorunmeyen runtime, schema, env, optimizer veya UI sonucu uydurulur

## Kabul Edilemez Hatalar

- payload shape kirilmasi
- no-leak cizgisinin bozulmasi
- Python test zincirinde final state veya assertion nedeni gibi kritik adimlarin kaybi
- heuristik alanlarda parser-backed kesinlik varmis gibi konusma

## Governance Notu

Scored goldens setinde su degisiklikler review gerektirir:

- case ekleme veya cikarma
- `coverage_tags` degisimi
- `good_output` / `bad_output` kontratinin zayiflamasi
- allowlist veya anti-hallucination beklentisinin gevsetilmesi
