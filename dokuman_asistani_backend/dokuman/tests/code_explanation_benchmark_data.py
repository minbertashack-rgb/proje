from __future__ import annotations


def _case(
    *,
    slug: str,
    axis: str,
    title: str,
    text: str,
    adres: str,
    meta: dict,
    minimum_explanation: str,
    good_output: list[str],
    bad_output: list[str],
    unacceptable_errors: list[str],
    segment_language: str,
    expected_segment_kinds: list[str],
    expected_segment_names: list[str] | None = None,
    required_keywords: dict[str, list[str]] | None = None,
    specific_terms: list[str] | None = None,
    min_counts: dict[str, int] | None = None,
    forbidden_generic_phrases: list[str] | None = None,
    hallucination_forbidden: list[str] | None = None,
    coverage_tags: list[str] | None = None,
) -> dict:
    return {
        "slug": slug,
        "axis": axis,
        "title": title,
        "text": text.strip("\n"),
        "adres": adres,
        "meta": dict(meta),
        "minimum_explanation": minimum_explanation,
        "good_output": list(good_output),
        "bad_output": list(bad_output),
        "unacceptable_errors": list(unacceptable_errors),
        "segment_language": segment_language,
        "expected_segment_kinds": list(expected_segment_kinds),
        "expected_segment_names": list(expected_segment_names or []),
        "required_keywords": dict(required_keywords or {}),
        "specific_terms": list(specific_terms or []),
        "min_counts": {
            "steps": 2,
            "glossary": 1,
            "block_comments": 1,
            "line_comments": 2,
            **dict(min_counts or {}),
        },
        "forbidden_generic_phrases": list(forbidden_generic_phrases or []),
        "hallucination_forbidden": list(hallucination_forbidden or []),
        "coverage_tags": list(coverage_tags or []),
    }


CODE_EXPLANATION_AXIS_MATRIX = {
    "python_test": {
        "label": "Python test",
        "strength": "parser_backed",
        "minimum_total": 12,
        "dimension_floor": {
            "accuracy": 2,
            "specificity": 2,
            "clarity": 2,
            "anti_generic": 1,
            "anti_hallucination": 2,
            "line_block_alignment": 2,
            "concise_readable": 1,
        },
        "notes": "En guclu eksen. Test step, assertion ve api_call meta'lari parser destekli okunuyor.",
    },
    "python_function": {
        "label": "Python function",
        "strength": "parser_backed",
        "minimum_total": 11,
        "dimension_floor": {
            "accuracy": 2,
            "specificity": 1,
            "clarity": 2,
            "anti_generic": 1,
            "anti_hallucination": 2,
            "line_block_alignment": 1,
            "concise_readable": 1,
        },
        "notes": "Fonksiyon ve control_flow ayrimi parser destekli. Veri donusumu ve return akisi beklenir.",
    },
    "python_class_method": {
        "label": "Python class/method",
        "strength": "parser_backed",
        "minimum_total": 11,
        "dimension_floor": {
            "accuracy": 2,
            "specificity": 1,
            "clarity": 2,
            "anti_generic": 1,
            "anti_hallucination": 2,
            "line_block_alignment": 1,
            "concise_readable": 1,
        },
        "notes": "State ve method ayrimi parser-backed, fakat niyet hala gorunen satirlardan cikartiliyor.",
    },
    "javascript_typescript": {
        "label": "JavaScript / TypeScript",
        "strength": "parser_like_heuristic",
        "minimum_total": 10,
        "dimension_floor": {
            "accuracy": 1,
            "specificity": 1,
            "clarity": 2,
            "anti_generic": 1,
            "anti_hallucination": 2,
            "line_block_alignment": 1,
            "concise_readable": 1,
        },
        "notes": "Fonksiyon, api_call ve assertion ayrimi regex/segment heuristikleriyle geliyor.",
    },
    "sql": {
        "label": "SQL",
        "strength": "clause_heuristic",
        "minimum_total": 10,
        "dimension_floor": {
            "accuracy": 1,
            "specificity": 1,
            "clarity": 2,
            "anti_generic": 1,
            "anti_hallucination": 2,
            "line_block_alignment": 1,
            "concise_readable": 1,
        },
        "notes": "Clause seviye okunur. CTE/subquery/window gibi ileri yapilar sadece gorunen kisim kadar anlatilmalidir.",
    },
    "html_css": {
        "label": "HTML / CSS",
        "strength": "structure_heuristic",
        "minimum_total": 9,
        "dimension_floor": {
            "accuracy": 1,
            "specificity": 1,
            "clarity": 1,
            "anti_generic": 1,
            "anti_hallucination": 2,
            "line_block_alignment": 1,
            "concise_readable": 1,
        },
        "notes": "Markup ve style ayrimi var; template/runtime davranisi uydurmak kabul edilmez.",
    },
    "json_yaml": {
        "label": "JSON / YAML",
        "strength": "key_value_heuristic",
        "minimum_total": 9,
        "dimension_floor": {
            "accuracy": 1,
            "specificity": 1,
            "clarity": 1,
            "anti_generic": 1,
            "anti_hallucination": 2,
            "line_block_alignment": 1,
            "concise_readable": 1,
        },
        "notes": "Section/group ve key-value aciklamasi beklenir; anchor/alias ve env etkisi uydurulamaz.",
    },
    "shell_ps1": {
        "label": "shell / ps1",
        "strength": "command_flow_heuristic",
        "minimum_total": 9,
        "dimension_floor": {
            "accuracy": 1,
            "specificity": 1,
            "clarity": 1,
            "anti_generic": 1,
            "anti_hallucination": 2,
            "line_block_alignment": 1,
            "concise_readable": 1,
        },
        "notes": "Function, variable, command/api ve control_flow aciklamasi beklenir; ortam sonucu kesinlestirilmez.",
    },
}


CODE_EXPLANATION_REQUIRED_COVERAGE_TAGS = {
    "drf_api_test",
    "authorization",
    "payload_chain",
    "mock",
    "monkeypatch",
    "helper_call",
    "chained_assert",
    "nested_block",
    "state_usage",
    "state_mutation",
    "sql_select",
    "sql_update",
    "js_event_handler",
    "js_nested_callback",
    "markup",
    "css",
    "yaml",
    "yaml_anchor_alias",
    "json",
    "config_flag",
    "powershell",
    "sql_cte_boundary",
}


CODE_EXPLANATION_BENCHMARK_CASES = [
    _case(
        slug="python_drf_api_test",
        axis="python_test",
        title="DRF API test chain",
        text="""
def test_author_can_create_document_with_hash(self):
    self.client.force_authenticate(user=self.author_user)
    data = {"title": "DocVerse Manifesto", "content": "Our mission is to manage docs."}
    response = self.client.post("/api/v1/author/documents/", data)
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    self.assertIn("version_hash", response.data)
    self.document.refresh_from_db()
    self.assertEqual(self.document.status, "DRAFT")
""",
        adres="code:python:test_function:1",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "python",
            "code_language": "python",
            "code_unit_kind": "test_function",
            "code_unit_name": "test_author_can_create_document_with_hash",
            "test_step_kind": "assertion",
            "line_start": 18,
            "line_end": 25,
        },
        segment_language="python",
        expected_segment_kinds=["test_function", "test_step", "assertion", "api_call"],
        expected_segment_names=["test_author_can_create_document_with_hash"],
        minimum_explanation="Hazirlik, yetkilendirme, payload, endpoint cagrisi, status assert, field assert ve final state assert zincirini ayirmali.",
        good_output=[
            "Hazirlik / Input / Cagri / Dogrulama fazlari ayrilir.",
            "Status assert ile version_hash alan assert ve final state assert farkli amaclarla anlatilir.",
        ],
        bad_output=[
            "Sadece endpointi kontrol ettigini soyler.",
            "refresh_from_db ve DRAFT state dogrulamasini atlar.",
        ],
        unacceptable_errors=["Yetkilendirme veya final state assertion'i atlamak.", "Kodda olmayan PATCH/DELETE davranisi uydurmak."],
        required_keywords={
            "steps": ["Hazirlik", "Input", "Cagri", "Dogrulama"],
            "flow_summary": ["hazirlik", "yetki", "payload", "final state"],
            "line_comments": ["yetkilendirir", "payload", "HTTP 201", "version_hash", "DRAFT"],
            "block_comments": ["Hazirlik", "Payload", "Assertion"],
        },
        specific_terms=["force_authenticate", "version_hash", "DRAFT", "POST"],
        min_counts={"steps": 4, "glossary": 3, "block_comments": 3, "line_comments": 5},
        forbidden_generic_phrases=["bu test endpointi kontrol ediyor", "bu test bir sey deniyor"],
        hallucination_forbidden=["DELETE", "PATCH", "admin onayi", "500 hatasi"],
        coverage_tags=["drf_api_test", "authorization", "payload_chain", "final_state_assert"],
    ),
    _case(
        slug="python_mock_monkeypatch_test",
        axis="python_test",
        title="Mock and monkeypatch test",
        text="""
def test_create_document_with_mock(api_client, author_user, monkeypatch):
    api_client.force_authenticate(user=author_user)
    monkeypatch.setattr(notifications, "send", fake_send)
    payload = {"title": "DocVerse"}
    response = api_client.post("/api/v1/documents/", payload, format="json")
    assert response.status_code == 201
    if response.data["status"] == "draft":
        assert response.data["title"] == "DocVerse"
    document.refresh_from_db()
    assert document.status == "draft"
""",
        adres="code:python:test_function:2",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "python",
            "code_language": "python",
            "code_unit_kind": "test_function",
            "code_unit_name": "test_create_document_with_mock",
            "test_step_kind": "assertion",
            "line_start": 40,
            "line_end": 49,
        },
        segment_language="python",
        expected_segment_kinds=["test_function", "test_step", "assertion", "api_call", "control_flow"],
        expected_segment_names=["test_create_document_with_mock"],
        minimum_explanation="Mock/monkeypatch'in testi deterministik yaptigini, kosullu assertion'i ve final state'i ayirmali.",
        good_output=[
            "mock satiri hazirlik olarak okunur.",
            "Kosullu assertion hangi response durumunda calistigini soyler.",
        ],
        bad_output=[
            "Monkeypatch'i gormezden gelir.",
            "If blogunu sadece kontrol var diyerek gecer.",
        ],
        unacceptable_errors=["mock satirini API cagrisi sanmak.", "Kodda olmayan retry veya exception akisi uydurmak."],
        required_keywords={
            "steps": ["Hazirlik", "Cagri", "Dogrulama"],
            "flow_summary": ["mock", "payload", "assert"],
            "line_comments": ["deterministik", "POST", "hangi kosul", "HTTP 201", "DRAFT"],
            "block_comments": ["Hazirlik", "Assertion", "Kosullu"],
        },
        specific_terms=["monkeypatch", "payload", "POST", "draft"],
        min_counts={"steps": 3, "glossary": 2, "block_comments": 3, "line_comments": 5},
        forbidden_generic_phrases=["testi kontrol eder", "durumu kontrol eder"],
        hallucination_forbidden=["email gonderir", "rollback", "DELETE"],
        coverage_tags=["mock", "monkeypatch", "nested_assert", "final_state_assert"],
    ),
    _case(
        slug="python_helper_assert_chain",
        axis="python_test",
        title="Helper plus chained assertions",
        text="""
def test_refresh_token_flow(client, token_factory):
    token = token_factory()
    response = client.post("/api/v1/token/refresh/", {"refresh": token})
    assert response.status_code == 200
    body = response.json()
    assert "access" in body
    assert body["access"] != token
""",
        adres="code:python:test_function:3",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "python",
            "code_language": "python",
            "code_unit_kind": "test_function",
            "code_unit_name": "test_refresh_token_flow",
            "test_step_kind": "assertion",
            "line_start": 10,
            "line_end": 16,
        },
        segment_language="python",
        expected_segment_kinds=["test_function", "test_step", "assertion", "api_call"],
        expected_segment_names=["test_refresh_token_flow"],
        minimum_explanation="Helper cagrisi, endpoint refresh cagrisi, status assert ve body icindeki chained assert nedenleri ayri anlatilmali.",
        good_output=[
            "token_factory hazirlik adimi olarak okunur.",
            "response.json ve access assertion'lari farkli dogrulama amaclariyla ayrilir.",
        ],
        bad_output=[
            "Tum assertion'lari tek kontrol diye toplar.",
            "Body assertion nedenlerini soylemez.",
        ],
        unacceptable_errors=["refresh endpoint yerine login endpointi demek.", "Kodda olmayan db state'i uydurmak."],
        required_keywords={
            "steps": ["Hazirlik", "Cagri", "Dogrulama"],
            "flow_summary": ["hazirlik", "payload", "assert"],
            "line_comments": ["payload", "HTTP 200", "access"],
            "block_comments": ["Temel", "Assertion"],
        },
        specific_terms=["token_factory", "refresh", "access", "HTTP 200"],
        min_counts={"steps": 3, "glossary": 2, "block_comments": 2, "line_comments": 4},
        forbidden_generic_phrases=["token akisina bakar", "sadece basariyi kontrol eder"],
        hallucination_forbidden=["logout", "DRAFT", "DELETE"],
        coverage_tags=["helper_call", "chained_assert", "payload_shape"],
    ),
    _case(
        slug="python_transform_function",
        axis="python_function",
        title="Normalization function",
        text="""
def normalize_username(raw_name):
    cleaned = raw_name.strip().lower()
    if not cleaned:
        return "anonymous"
    return cleaned.replace(" ", "_")
""",
        adres="code:python:function:1",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "python",
            "code_language": "python",
            "code_unit_kind": "function",
            "code_unit_name": "normalize_username",
            "line_start": 40,
            "line_end": 44,
        },
        segment_language="python",
        expected_segment_kinds=["function", "control_flow"],
        expected_segment_names=["normalize_username"],
        minimum_explanation="Girdi, normalize etme, bos input branch'i ve iki farkli return sonucu anlatilmali.",
        good_output=["strip/lower donusumu ve anonymous branch'i ayrilir."],
        bad_output=["Sadece string isler der.", "Bos branch'i atlar."],
        unacceptable_errors=["Regex veya database kontrolu uydurmak."],
        required_keywords={
            "steps": ["Girdi", "Islem", "Beklenen sonuc"],
            "function_purpose": ["input", "ana islemi", "sonucu dondurur"],
            "flow_summary": ["girdi", "donusum", "kosul", "donus"],
            "line_comments": ["normalize", "hangi dalin", "dondurur"],
        },
        specific_terms=["normalize_username", "anonymous", "replace", "raw_name"],
        min_counts={"steps": 3, "glossary": 2, "block_comments": 2, "line_comments": 3},
        forbidden_generic_phrases=["string isler", "bir donusum yapar"],
        hallucination_forbidden=["database", "network", "cache"],
        coverage_tags=["transformation_function", "return_branch"],
    ),
    _case(
        slug="python_nested_loop_function",
        axis="python_function",
        title="Nested loop and branch function",
        text="""
def collect_active_ids(users):
    active_ids = []
    for user in users:
        if user["active"]:
            active_ids.append(user["id"])
    return active_ids
""",
        adres="code:python:function:2",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "python",
            "code_language": "python",
            "code_unit_kind": "function",
            "code_unit_name": "collect_active_ids",
            "line_start": 90,
            "line_end": 95,
        },
        segment_language="python",
        expected_segment_kinds=["function", "control_flow"],
        expected_segment_names=["collect_active_ids"],
        minimum_explanation="Iterasyon ve kosul blogu ayrilmali; sadece active olan kullanicilarin id'lerinin toplandigi soylenmeli.",
        good_output=["Iterasyon ve hangi dalin sonucu degistirdigi belirtilir."],
        bad_output=["Liste olusturur deyip kosulu atlar."],
        unacceptable_errors=["Siralama yaptigini veya filtreledigi alanlari uydurmak."],
        required_keywords={
            "flow_summary": ["iterasyon", "kosul", "donus"],
            "block_comments": ["Iterasyon", "Kosul"],
            "line_comments": ["iterasyonu baslatir", "hangi dalin", "dondurur"],
        },
        specific_terms=["active_ids", "users", "active", "id"],
        min_counts={"steps": 3, "glossary": 1, "block_comments": 3, "line_comments": 4},
        forbidden_generic_phrases=["listeyi yonetir", "veriyi kontrol eder"],
        hallucination_forbidden=["sort", "database", "cache"],
        coverage_tags=["nested_block", "loop_condition"],
    ),
    _case(
        slug="python_stateful_class",
        axis="python_class_method",
        title="State holding class",
        text="""
class Cart:
    def __init__(self, items):
        self.items = items

    def total(self):
        return sum(item["price"] for item in self.items)
""",
        adres="code:python:class:1",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "python",
            "code_language": "python",
            "code_unit_kind": "class",
            "code_unit_name": "Cart",
            "line_start": 60,
            "line_end": 65,
        },
        segment_language="python",
        expected_segment_kinds=["class", "method"],
        expected_segment_names=["Cart", "total"],
        minimum_explanation="Kurulum, self.items state'i ve total method'unun bu state uzerinden sonuc urettigi ayrilmali.",
        good_output=["__init__ ile total ayni sorumluluk gibi anlatilmaz."],
        bad_output=["Sinif veri tutuyor demekle yetinir."],
        unacceptable_errors=["Odeme yaptigini veya veritabani yazdirdigini uydurmak."],
        required_keywords={
            "steps": ["Kurulum", "Metotlar", "Durum kullanimi"],
            "function_purpose": ["sinif", "state", "metot"],
            "line_comments": ["__init__", "self.items", "dondurur"],
        },
        specific_terms=["Cart", "self.items", "total", "price"],
        min_counts={"steps": 3, "glossary": 2, "block_comments": 2, "line_comments": 3},
        forbidden_generic_phrases=["sinifi aciklar", "veriyi kontrol eder"],
        hallucination_forbidden=["checkout", "database", "API"],
        coverage_tags=["class_setup", "state_usage"],
    ),
    _case(
        slug="python_state_mutation_method",
        axis="python_class_method",
        title="State mutating method",
        text="""
class Cart:
    def add_item(self, item):
        if not item:
            return None
        self.items = self.items + [item]
        return len(self.items)
""",
        adres="code:python:method:1",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "python",
            "code_language": "python",
            "code_unit_kind": "method",
            "code_unit_name": "add_item",
            "parent_unit": "Cart",
            "line_start": 70,
            "line_end": 75,
        },
        segment_language="python",
        expected_segment_kinds=["class", "method", "control_flow"],
        expected_segment_names=["Cart", "add_item"],
        minimum_explanation="Bos item branch'i, self.items state mutation'i ve return edilen yeni boyut ayni akista gorunmeli.",
        good_output=["State degisimi ile return degeri baglanir."],
        bad_output=["Sadece item ekler deyip kosul ve return sonucunu atlar."],
        unacceptable_errors=["Silme veya db persist ettigini uydurmak."],
        required_keywords={
            "function_purpose": ["input", "ana islemi", "sonucu dondurur"],
            "flow_summary": ["kosul", "state", "donus"],
            "line_comments": ["state degisimi", "hangi dalin", "dondurur"],
        },
        specific_terms=["add_item", "self.items", "len", "item"],
        min_counts={"steps": 3, "glossary": 2, "block_comments": 2, "line_comments": 3},
        forbidden_generic_phrases=["method bir sey yapar", "itemi kontrol eder"],
        hallucination_forbidden=["save()", "database", "checkout"],
        coverage_tags=["state_mutation", "branch"],
    ),
    _case(
        slug="sql_select_join_filter",
        axis="sql",
        title="SQL select join filter",
        text="""
SELECT orders.id, customers.email, orders.total_amount
FROM orders
JOIN customers ON customers.id = orders.customer_id
WHERE orders.status = 'APPROVED';
""",
        adres="code:sql:select:1",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "sql",
            "code_language": "sql",
            "code_unit_kind": "sql_select",
            "code_unit_name": "approved_orders_with_customer",
            "line_start": 5,
            "line_end": 8,
        },
        segment_language="sql",
        expected_segment_kinds=["sql_select", "sql_from_join", "sql_where_group"],
        expected_segment_names=["select_orders", "from_join_orders", "where_group_clause"],
        minimum_explanation="SELECT, FROM, JOIN ve WHERE akisinin her birini ayri aciklamali.",
        good_output=["JOIN iliskisi ve WHERE filtresi clause bazinda gorunur."],
        bad_output=["Sadece onayli siparisleri getiriyor deyip JOIN'i yok sayar."],
        unacceptable_errors=["Kodda olmayan GROUP BY veya aggregate sonucu uydurmak."],
        required_keywords={
            "steps": ["Secim", "Kaynak", "Filtre"],
            "flow_summary": ["SELECT", "FROM", "JOIN", "WHERE"],
            "line_comments": ["kolonlari", "tabloyu", "JOIN", "filtreler"],
        },
        specific_terms=["SELECT", "JOIN", "customers", "APPROVED"],
        min_counts={"steps": 3, "glossary": 2, "block_comments": 1, "line_comments": 4},
        forbidden_generic_phrases=["veri getirir", "sorgu calisir"],
        hallucination_forbidden=["GROUP BY", "window", "subquery"],
        coverage_tags=["sql_select", "join", "filter"],
    ),
    _case(
        slug="sql_update_filter",
        axis="sql",
        title="SQL update/delete style write query",
        text="""
UPDATE users
SET active = 0
WHERE last_login < '2024-01-01';
""",
        adres="code:sql:update:1",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "sql",
            "code_language": "sql",
            "code_unit_kind": "sql_update",
            "code_unit_name": "deactivate_old_users",
            "line_start": 30,
            "line_end": 32,
        },
        segment_language="sql",
        expected_segment_kinds=["sql_update", "sql_where_group"],
        expected_segment_names=["update_users"],
        minimum_explanation="Yazma etkisi, hedef tablo ve WHERE kapsam siniri belirtilmeli.",
        good_output=["Statement purpose ve filter ayri anlatilir."],
        bad_output=["Sadece kullanicilari guncelliyor der."],
        unacceptable_errors=["Tum kullanicilari silecegini veya transaction davranisi uydurmak."],
        required_keywords={
            "steps": ["Statement purpose", "Filter"],
            "flow_summary": ["statement purpose", "hedef tablo", "yazma etkisi"],
            "line_comments": ["hedef tablo", "gunceller"],
        },
        specific_terms=["UPDATE", "users", "active", "WHERE"],
        min_counts={"steps": 2, "glossary": 1, "block_comments": 1, "line_comments": 1},
        forbidden_generic_phrases=["sql calisir", "durumu kontrol eder"],
        hallucination_forbidden=["DELETE", "rollback", "insert"],
        coverage_tags=["sql_update", "write_query"],
    ),
    _case(
        slug="js_event_handler",
        axis="javascript_typescript",
        title="JS event handler",
        text="""
function handleMenuToggle(event) {
  event.preventDefault();
  setOpen(true);
  return renderMenu();
}
""",
        adres="code:javascript:function:1",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "javascript",
            "code_language": "javascript",
            "code_unit_kind": "function",
            "code_unit_name": "handleMenuToggle",
            "line_start": 12,
            "line_end": 15,
        },
        segment_language="javascript",
        expected_segment_kinds=["function"],
        expected_segment_names=["handleMenuToggle"],
        minimum_explanation="Event, state guncelleme ve render sonucu ayri anlatilmali.",
        good_output=["preventDefault -> state -> render akisi kurulur."],
        bad_output=["Sadece tiklama fonksiyonudur denir."],
        unacceptable_errors=["Kodda olmayan network istegi uydurmak."],
        required_keywords={
            "steps": ["Girdi", "Islem", "Beklenen sonuc"],
            "flow_summary": ["event", "state", "render"],
            "line_comments": ["kontrolu koda verir", "arayuz durumunu gunceller", "render"],
        },
        specific_terms=["event", "setOpen", "render", "preventDefault"],
        min_counts={"steps": 3, "glossary": 1, "block_comments": 2, "line_comments": 3},
        forbidden_generic_phrases=["formu yonetir", "bir butonu kontrol eder"],
        hallucination_forbidden=["fetch", "axios", "database"],
        coverage_tags=["js_event_handler", "event_handler", "frontend_state"],
    ),
    _case(
        slug="js_api_state_change",
        axis="javascript_typescript",
        title="JS API call and state change",
        text="""
async function handleSubmit(event) {
  event.preventDefault();
  const response = await fetch("/api/save", { method: "POST" });
  setSaved(true);
  return <SuccessBanner saved={saved} />;
}
""",
        adres="code:javascript:function:2",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "javascript",
            "code_language": "javascript",
            "code_unit_kind": "function",
            "code_unit_name": "handleSubmit",
            "line_start": 70,
            "line_end": 74,
        },
        segment_language="javascript",
        expected_segment_kinds=["function", "api_call"],
        expected_segment_names=["handleSubmit"],
        minimum_explanation="Event, fetch API cagrisi, state degisimi ve render edilen banner birlikte okunmali.",
        good_output=["API ve state blogu ayrilir, render son adim olarak baglanir."],
        bad_output=["Sadece form gonderir der."],
        unacceptable_errors=["Kodda olmayan retry veya hata handling uydurmak."],
        required_keywords={
            "steps": ["Girdi", "Islem", "Beklenen sonuc"],
            "function_purpose": ["event", "API", "UI sonucuna"],
            "flow_summary": ["event", "state", "api", "render"],
            "line_comments": ["API cagrisi", "arayuz durumunu gunceller", "render"],
        },
        specific_terms=["event", "API", "state", "render"],
        min_counts={"steps": 3, "glossary": 1, "block_comments": 2, "line_comments": 4},
        forbidden_generic_phrases=["formu gonderir", "ekrani yonetir"],
        hallucination_forbidden=["redirect", "toast", "database"],
        coverage_tags=["api_call", "frontend_state", "render"],
    ),
    _case(
        slug="js_nested_callback_handler",
        axis="javascript_typescript",
        title="JS nested callback with API and state",
        text="""
function setupSave(button) {
  button.addEventListener("click", async () => {
    const response = await fetch("/api/save");
    if (response.ok) { setSaved(true); }
  });
}
""",
        adres="code:javascript:function:9",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "javascript",
            "code_language": "javascript",
            "code_unit_kind": "function",
            "code_unit_name": "setupSave",
            "line_start": 1,
            "line_end": 5,
        },
        segment_language="javascript",
        expected_segment_kinds=["function", "api_call", "control_flow"],
        expected_segment_names=["setupSave", "click_handler"],
        minimum_explanation="Parent function, nested click callback, fetch cagrisi ve state degisimi ayni akis icinde ama karismadan anlatilmali.",
        good_output=[
            "Nested callback ile dis function ayrilir.",
            "API cagrisi ile response.ok kosulu state guncellemesinden once anlatilir.",
        ],
        bad_output=[
            "Tum blogu tek tiklama handler'i diye gecer.",
            "response.ok kosulunu veya setSaved state degisimini atlar.",
        ],
        unacceptable_errors=["Kodda olmayan toast, redirect veya hata handling akisi uydurmak."],
        required_keywords={
            "steps": ["Girdi", "Islem", "Beklenen sonuc"],
            "function_purpose": ["event", "API", "state sonucuna"],
            "flow_summary": ["event", "state", "api", "kosul"],
            "line_comments": ["click", "API cagrisi", "state guncellemesi"],
            "block_comments": ["Handler", "Kosul"],
        },
        specific_terms=["addEventListener", "fetch", "setSaved", "response.ok"],
        min_counts={"steps": 3, "glossary": 1, "block_comments": 2, "line_comments": 2},
        forbidden_generic_phrases=["bir butonu kontrol eder", "ekrani yonetir"],
        hallucination_forbidden=["toast", "redirect", "database"],
        coverage_tags=["js_nested_callback", "api_call", "frontend_state", "callback_condition"],
    ),
    _case(
        slug="html_markup_block",
        axis="html_css",
        title="HTML markup block",
        text="""
<section>
  <form>
    <input />
  </form>
</section>
""",
        adres="code:html:markup:1",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "html",
            "code_language": "html",
            "code_unit_kind": "markup_block",
            "code_unit_name": "section",
            "line_start": 10,
            "line_end": 14,
        },
        segment_language="html",
        expected_segment_kinds=["markup_block"],
        expected_segment_names=["section", "form", "input"],
        minimum_explanation="Markup iskeleti, form blogu ve input alani yapisal olarak anlatilmali; script davranisi uydurulmamali.",
        good_output=["Tag hiyerarsisi ve form/input rolleri ayri gorunur."],
        bad_output=["Form gonderir deyip script davranisi uydurur."],
        unacceptable_errors=["Validation veya API davranisi uydurmak."],
        required_keywords={
            "steps": ["Markup block", "Ic bloklar"],
            "function_purpose": ["sayfa iskeletini"],
            "flow_summary": ["semantic", "bloklar"],
            "line_comments": ["markup iskeleti", "input alanini"],
        },
        specific_terms=["section", "form", "input", "markup"],
        min_counts={"steps": 2, "glossary": 1, "block_comments": 1, "line_comments": 2},
        forbidden_generic_phrases=["formu gonderir", "butona basinca"],
        hallucination_forbidden=["fetch", "state", "onClick"],
        coverage_tags=["markup", "html_structure"],
    ),
    _case(
        slug="css_style_rule",
        axis="html_css",
        title="CSS style rule",
        text="""
.notice {
  color: red;
  display: flex;
  gap: 8px;
}
""",
        adres="code:css:style:1",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "css",
            "code_language": "css",
            "code_unit_kind": "style_rule",
            "code_unit_name": ".notice",
            "line_start": 20,
            "line_end": 24,
        },
        segment_language="css",
        expected_segment_kinds=["style_rule"],
        expected_segment_names=[".notice"],
        minimum_explanation="Secici, stil kurallari ve layout/spacing gibi gorunen etkiler anlatilmali.",
        good_output=["selector, layout ve spacing property'leri birlikte geciyor."],
        bad_output=["Animasyon veya event davranisi uyduruyor."],
        unacceptable_errors=["Kodda olmayan hover/js etkisi uydurmak."],
        required_keywords={
            "steps": ["Secici", "Kurallar", "Beklenen etki"],
            "function_purpose": ["style", "layout", "gorunum etkisi"],
            "flow_summary": ["selector", "layout", "spacing"],
            "line_comments": ["secicisine stil", "color", "display", "gap"],
        },
        specific_terms=[".notice", "color", "display", "gap", "selector"],
        min_counts={"steps": 3, "glossary": 1, "block_comments": 1, "line_comments": 3},
        forbidden_generic_phrases=["sayfayi duzenler", "uiyi yonetir"],
        hallucination_forbidden=["fetch", "click", "state"],
        coverage_tags=["css", "style_rule"],
    ),
    _case(
        slug="yaml_config_section",
        axis="json_yaml",
        title="YAML config section",
        text="""
service:
  base_url: https://api.example.test
  timeout: 30
logging:
  level: info
""",
        adres="code:yaml:section:1",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "yaml",
            "code_language": "yaml",
            "code_unit_kind": "section",
            "code_unit_name": "service",
            "code_purpose_hints": ["config", "network"],
            "line_start": 1,
            "line_end": 5,
        },
        segment_language="yaml",
        expected_segment_kinds=["config_entry"],
        expected_segment_names=["service", "base_url", "timeout", "logging", "level"],
        minimum_explanation="section/group ve gorunen key-value satirlari ayirmali; ortamsal env davranisi uydurmamali.",
        good_output=["service, base_url ve timeout gibi gorunen anahtarlar ayrilir."],
        bad_output=["Deployment davranisi uydurur."],
        unacceptable_errors=["Kodda olmayan secret/env override etkisi uydurmak."],
        required_keywords={
            "steps": ["Group/section", "Gorunen anahtarlar"],
            "function_purpose": ["anahtar-deger", "ayar amaci"],
            "flow_summary": ["config anahtari", "gorunen deger"],
            "line_comments": ["service", "base_url", "timeout"],
        },
        specific_terms=["service", "base_url", "timeout", "logging"],
        min_counts={"steps": 2, "glossary": 2, "block_comments": 1, "line_comments": 3},
        forbidden_generic_phrases=["ayar dosyasidir", "servisi calistirir"],
        hallucination_forbidden=["environment variable", "anchor merge", "docker"],
        coverage_tags=["yaml", "config_section"],
    ),
    _case(
        slug="yaml_anchor_alias_section",
        axis="json_yaml",
        title="YAML anchor and alias boundary",
        text="""
defaults: &defaults
  timeout: 30
service:
  <<: *defaults
  base_url: https://api.example.test
""",
        adres="code:yaml:section:9",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "yaml",
            "code_language": "yaml",
            "code_unit_kind": "section",
            "code_unit_name": "service",
            "code_purpose_hints": ["config", "network"],
            "line_start": 1,
            "line_end": 5,
        },
        segment_language="yaml",
        expected_segment_kinds=["section", "config_entry"],
        expected_segment_names=["defaults", "timeout", "service", "base_url"],
        minimum_explanation="Gorunen section ve key-value satirlari ayirmali; anchor/alias var diye gorunmeyen merge sonucunu kesinlestirmemeli.",
        good_output=[
            "defaults, service, timeout ve base_url gibi gorunen kisimlar tek tek ayrilir.",
            "Alias/merge tarafinda parser gucu varmis gibi kesin konusmaz.",
        ],
        bad_output=[
            "Tum merge sonucunu aciklanmis kabul eder.",
            "Environment veya deployment davranisi uydurur.",
        ],
        unacceptable_errors=["Kodda gorunmeyen merge sonucu, env override veya docker davranisi uydurmak."],
        required_keywords={
            "steps": ["Group/section", "Gorunen anahtarlar"],
            "function_purpose": ["anahtar-deger", "ayar amaci"],
            "flow_summary": ["config anahtari", "gorunen deger"],
            "line_comments": ["defaults", "timeout", "service", "base_url"],
            "block_comments": ["Config grubu"],
        },
        specific_terms=["defaults", "timeout", "service", "base_url"],
        min_counts={"steps": 2, "glossary": 1, "block_comments": 1, "line_comments": 4},
        forbidden_generic_phrases=["ayar dosyasidir", "servisi calistirir"],
        hallucination_forbidden=["environment variable", "docker", "merge sonucu"],
        coverage_tags=["yaml", "yaml_anchor_alias", "config_section"],
    ),
    _case(
        slug="json_config_entry",
        axis="json_yaml",
        title="JSON config entry",
        text="""
{
  "api": {
    "base": "/v1",
    "token": "secret"
  }
}
""",
        adres="code:json:section:1",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "json",
            "code_language": "json",
            "code_unit_kind": "section",
            "code_unit_name": "api",
            "code_purpose_hints": ["config", "network"],
            "line_start": 1,
            "line_end": 6,
        },
        segment_language="json",
        expected_segment_kinds=["config_entry"],
        expected_segment_names=["api", "base", "token"],
        minimum_explanation="api section'i ve key-value satirlari ayirmali; token icin kodda olmayan guvenlik politikasi uydurmamali.",
        good_output=["section ve key-value aciklamasi ayridir."],
        bad_output=["Secret rotation gibi gorunmeyen politikalari anlatir."],
        unacceptable_errors=["Kodda olmayan auth flow'u uydurmak."],
        required_keywords={
            "steps": ["Group/section", "Gorunen anahtarlar"],
            "function_purpose": ["anahtar-deger"],
            "flow_summary": ["config anahtari", "section"],
            "line_comments": ["base", "token"],
        },
        specific_terms=["api", "base", "token", "config"],
        min_counts={"steps": 2, "glossary": 2, "block_comments": 1, "line_comments": 2},
        forbidden_generic_phrases=["ayar tutar", "networku kontrol eder"],
        hallucination_forbidden=["refresh token", "oauth", "database"],
        coverage_tags=["json", "config_entry"],
    ),
    _case(
        slug="json_feature_flags_section",
        axis="json_yaml",
        title="JSON feature flags section",
        text="""
{
  "features": {
    "beta": true,
    "api_base": "/v2"
  }
}
""",
        adres="code:json:section:9",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "json",
            "code_language": "json",
            "code_unit_kind": "section",
            "code_unit_name": "features",
            "code_purpose_hints": ["config", "network"],
            "line_start": 1,
            "line_end": 6,
        },
        segment_language="json",
        expected_segment_kinds=["section", "config_entry"],
        expected_segment_names=["features", "beta", "api_base"],
        minimum_explanation="Feature flag section'i ile gorunen anahtarlar ayri anlatilmali; beta veya api_base uzerinden gorunmeyen rollout/policy uydurulmamali.",
        good_output=[
            "Section ve alt key-value satirlari ayri okunur.",
            "boolean flag ile path benzeri deger farkli amaclarla anlatilir.",
        ],
        bad_output=[
            "Tum rollout politikasini bildigini varsayar.",
            "Auth veya database akisi uydurur.",
        ],
        unacceptable_errors=["Kodda gorunmeyen rollout, auth flow veya persistence davranisi uydurmak."],
        required_keywords={
            "steps": ["Group/section", "Gorunen anahtarlar"],
            "function_purpose": ["anahtar-deger", "ayar amaci"],
            "flow_summary": ["config anahtari", "section"],
            "line_comments": ["features", "beta", "api_base"],
            "block_comments": ["Config grubu"],
        },
        specific_terms=["features", "beta", "api_base", "config"],
        min_counts={"steps": 2, "glossary": 1, "block_comments": 1, "line_comments": 3},
        forbidden_generic_phrases=["ayar tutar", "networku kontrol eder"],
        hallucination_forbidden=["oauth", "refresh token", "database"],
        coverage_tags=["json", "config_flag", "config_entry"],
    ),
    _case(
        slug="sql_cte_rank_filter",
        axis="sql",
        title="SQL CTE and rank boundary",
        text="""
WITH ranked AS (
  SELECT user_id, score, ROW_NUMBER() OVER (PARTITION BY team_id ORDER BY score DESC) AS rn
  FROM scores
)
SELECT user_id, score FROM ranked WHERE rn = 1;
""",
        adres="code:sql:select:9",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "sql",
            "code_language": "sql",
            "code_unit_kind": "sql_select",
            "code_unit_name": "ranked_scores",
            "line_start": 1,
            "line_end": 5,
        },
        segment_language="sql",
        expected_segment_kinds=["sql_with", "sql_select", "sql_from_join"],
        expected_segment_names=["with_scores", "select_ranked", "from_join_scores"],
        minimum_explanation="CTE ve gorunen filtre zincirini anlatmali; ama window function sonucu veya optimizer davranisini kesinlestirmemeli.",
        good_output=[
            "SELECT/FROM/WHERE akisina bagli kalir.",
            "Gorunmeyen veri sonucu veya optimizer davranisi uydurmaz.",
        ],
        bad_output=[
            "Window function sonucu ve ranking semantiğini fazlasiyla kesinlestirir.",
            "Materialized CTE veya execution plan anlatir.",
        ],
        unacceptable_errors=["Kodda gorunmeyen optimizer, materialize veya kesin sonuc seti yorumu uydurmak."],
        required_keywords={
            "steps": ["Secim", "Kaynak", "Filtre"],
            "flow_summary": ["SELECT", "FROM", "WHERE"],
            "line_comments": ["kolonlari", "tabloyu", "filtreler"],
            "block_comments": ["Sorgu"],
        },
        specific_terms=["SELECT", "scores", "ranked", "rn"],
        min_counts={"steps": 3, "glossary": 1, "block_comments": 1, "line_comments": 2},
        forbidden_generic_phrases=["veri getirir", "sorgu calisir"],
        hallucination_forbidden=["optimizer", "materialized"],
        coverage_tags=["sql", "sql_cte_boundary", "filter"],
    ),
    _case(
        slug="html_markup_script_style_split",
        axis="html_css",
        title="HTML markup plus script/style split",
        text="""
<section>
  <style>
    .notice { color: red; }
  </style>
  <form>
    <input />
  </form>
  <script>
    fetch('/api/save')
  </script>
</section>
""",
        adres="code:html:markup:9",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "html",
            "code_language": "html",
            "code_unit_kind": "markup_block",
            "code_unit_name": "section",
            "line_start": 1,
            "line_end": 10,
        },
        segment_language="html",
        expected_segment_kinds=["markup_block", "style_block", "script_block", "api_call"],
        expected_segment_names=["section", "style", "script"],
        minimum_explanation="Markup, style ve script bloklarini ayirmali; script davranisini gorunmeyen runtime'a genisletmemeli.",
        good_output=[
            "Markup iskeleti ile style/script bloklari ayri anlatilir.",
            "fetch satiri script blogu icinde kalir; style kurali davranisla karistirilmaz.",
        ],
        bad_output=[
            "Tum HTML blogunu tek tip duz metin gibi anlatir.",
            "Validation veya framework runtime'i uydurur.",
        ],
        unacceptable_errors=["Kodda olmayan event binding, state veya framework davranisi uydurmak."],
        required_keywords={
            "steps": ["Markup block", "Ic bloklar"],
            "function_purpose": ["sayfa iskeletini"],
            "flow_summary": ["tagler", "bloklar"],
            "line_comments": ["script blogunu", "style blogunu", "input alanini"],
        },
        specific_terms=["section", "style", "script", "fetch"],
        min_counts={"steps": 2, "glossary": 1, "block_comments": 1, "line_comments": 3},
        forbidden_generic_phrases=["formu gonderir", "uygulamayi calistirir"],
        hallucination_forbidden=["Vue", "React state", "validation"],
        coverage_tags=["markup", "script_style_split", "html_structure"],
    ),
    _case(
        slug="powershell_external_call",
        axis="shell_ps1",
        title="PowerShell external API call",
        text="""
function Invoke-Test {
  $endpoint = "https://example.test"
  $response = Invoke-RestMethod -Uri $endpoint
  if ($response.ok) { Write-Host "ok" }
}
""",
        adres="code:powershell:function:1",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "powershell",
            "code_language": "powershell",
            "code_unit_kind": "function",
            "code_unit_name": "Invoke-Test",
            "code_purpose_hints": ["shell", "api_call"],
            "line_start": 20,
            "line_end": 24,
        },
        segment_language="powershell",
        expected_segment_kinds=["function", "variable", "api_call", "control_flow"],
        expected_segment_names=["Invoke-Test", "endpoint", "Invoke-RestMethod"],
        minimum_explanation="Function, endpoint degiskeni, dis cagrisi ve if kontrol akisi ayri anlatilmali.",
        good_output=["command/api ve kontrol akisi ayrilir."],
        bad_output=["Komutun sonucunu kesinlestirir."],
        unacceptable_errors=["200 dondu, servis ayakta gibi gorunmeyen sonuc uydurmak."],
        required_keywords={
            "steps": ["Function", "Command/API", "Kontrol akisi"],
            "function_purpose": ["sirali sekilde", "kontrol akisina"],
            "flow_summary": ["degisken", "command/api", "kontrol akisi"],
            "line_comments": ["endpoint", "Invoke-RestMethod", "kontrol akisi"],
        },
        specific_terms=["Invoke-Test", "endpoint", "Invoke-RestMethod", "response.ok"],
        min_counts={"steps": 3, "glossary": 1, "block_comments": 1, "line_comments": 3},
        forbidden_generic_phrases=["komutu calistirir", "kontrol eder"],
        hallucination_forbidden=["200 OK dondu", "dosyaya yazar", "retry"],
        coverage_tags=["powershell", "external_call", "control_flow"],
    ),
    _case(
        slug="shell_pipeline_external_call",
        axis="shell_ps1",
        title="Shell pipeline plus external call",
        text="""
function Sync-Items {
  $endpoint = "https://example.test/items"
  curl $endpoint | jq '.items'
  if ($LASTEXITCODE -ne 0) { Write-Host "fail" }
}
""",
        adres="code:powershell:function:9",
        meta={
            "format": "code",
            "chunk_kind": "code_block",
            "language": "powershell",
            "code_language": "powershell",
            "code_unit_kind": "function",
            "code_unit_name": "Sync-Items",
            "code_purpose_hints": ["shell", "api_call"],
            "line_start": 1,
            "line_end": 5,
        },
        segment_language="powershell",
        expected_segment_kinds=["function", "variable", "api_call", "control_flow"],
        expected_segment_names=["Sync-Items", "endpoint", "curl"],
        minimum_explanation="Degisken, dis cagrisi, pipeline ve kontrol akisi sirayla anlatilmali; komut sonucunu kesinlestirmemeli.",
        good_output=[
            "curl ve jq zinciri veri akisi olarak anlatilir.",
            "if blogu komut sonucu kontrolu olarak ayrilir.",
        ],
        bad_output=[
            "Servisin kesin calistigini veya belirli bir cikti dondurdugunu soyler.",
            "Pipeline adimini atlar.",
        ],
        unacceptable_errors=["200 dondu, jq su alanlari garanti etti gibi gorunmeyen sonuc uydurmak."],
        required_keywords={
            "steps": ["Function", "Hazirlik", "Command/API", "Kontrol akisi"],
            "function_purpose": ["sirali sekilde", "degiskenleri hazirlar"],
            "flow_summary": ["function", "degisken", "command/api", "kontrol akisi"],
            "line_comments": ["endpoint", "curl", "kontrol akisi"],
        },
        specific_terms=["Sync-Items", "endpoint", "curl", "jq"],
        min_counts={"steps": 4, "glossary": 1, "block_comments": 2, "line_comments": 3},
        forbidden_generic_phrases=["komutu calistirir", "kontrol eder"],
        hallucination_forbidden=["200 OK dondu", "dosyaya yazar", "retry"],
        coverage_tags=["powershell", "pipeline", "external_call"],
    ),
]
