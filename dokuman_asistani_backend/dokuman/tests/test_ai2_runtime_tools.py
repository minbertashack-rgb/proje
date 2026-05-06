from __future__ import annotations

import json
from collections import Counter

from dokuman.ai2.prompts import build_anlamadim_prompt
from tools.ai2_runtime import _infer_load_stage, probe_ai2_ready, resolve_default_model_path
from tools.run_anlamadim_live_batch import _build_summary


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self):
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_probe_ai2_ready_aliasi_dogrular(monkeypatch):
    payload = {"data": [{"id": "qwen-docverse"}]}

    def fake_urlopen(request, timeout=0):
        return _FakeResponse(payload, status=200)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    status = probe_ai2_ready("http://127.0.0.1:8002", timeout_sec=3, expected_alias="qwen-docverse")

    assert status["ready"] is True
    assert status["http_status"] == 200
    assert "qwen-docverse" in status["model_ids"]


def test_resolve_default_model_path_q5_varsayilanini_tercih_eder(monkeypatch):
    class _FakeCandidate:
        def __init__(self, label: str, exists: bool):
            self.label = label
            self._exists = exists

        def exists(self):
            return self._exists

        def __str__(self):
            return self.label

    q5 = _FakeCandidate("Q5", True)
    q4 = _FakeCandidate("Q4", True)
    deepseek = _FakeCandidate("Q6", True)
    monkeypatch.setattr(
        "tools.ai2_runtime._default_model_candidates",
        lambda: [q5, q4, deepseek],
    )

    resolved = resolve_default_model_path()

    assert resolved is q5


def test_live_batch_summary_turkce_alanlari_ve_sureyi_yazar():
    results = [
        {"score": 7, "response_sec": 12.5, "piece_kind": "plain_text"},
        {"score": 5, "response_sec": 7.5, "piece_kind": "numeric_row"},
    ]
    problem_counter = Counter(
        {
            "weak_one_liner": 1,
            "weak_very_simple": 1,
            "weak_glossary": 0,
            "weak_steps": 0,
            "weak_examples": 0,
            "weak_mini_quiz": 0,
            "false_dokumanda_yok": 0,
        }
    )
    ai2_status = {"ready": True, "startup_action": "already_running"}

    summary = _build_summary(results, problem_counter, "internal", ai2_status)

    assert summary["toplam_parca"] == 2
    assert summary["ortalama_skor"] == 6.0
    assert summary["weak_one_liner"] == 1
    assert summary["weak_very_simple"] == 1
    assert summary["ortalama_cevap_suresi"] == 10.0
    assert summary["min_cevap_suresi"] == 7.5
    assert summary["max_cevap_suresi"] == 12.5
    assert summary["transport_turu"] == "internal"
    assert summary["ai2_hazirlik_durumu"]["ready"] is True
    assert "avg_response_by_piece_kind" in summary
    assert summary["parca_tipi_dagilimi"]["plain_text"] == 1


def test_infer_load_stage_repack_asamasini_gorur():
    stderr_text = "load_tensors: layer 1 assigned\nrepack: repack tensor blk.0.attn_q.weight"
    stdout_text = ""

    stage = _infer_load_stage(stderr_text, stdout_text)

    assert stage == "model_repack"


def test_build_anlamadim_prompt_meta_kisa_parcayi_ve_prompt_yukunu_raporlar():
    messages, meta = build_anlamadim_prompt(
        "1",
        "JWT access token kullanicinin kimligini tasir ve refresh token ile yenilenir.",
        7,
        {"tema": "genel", "tarz": "kisa", "seviye": "baslangic", "mesaj": "Bu parcayi cok basit anlat."},
        return_meta=True,
    )

    assert len(messages) == 2
    assert meta["parca_sinifi"] == "kisa"
    assert meta["kisa_parca_mi"] is True
    assert meta["istenen_alan_sayisi"] == 7
    assert meta["prompt_parca_metin_uzunlugu"] <= meta["parca_metin_uzunlugu"]


def test_build_anlamadim_prompt_meta_uzun_parcayi_kisaltir():
    long_text = ("JWT access token kullanicinin kimligini tasir ve API cagrilarinda kullanilir. " * 40).strip()

    _, meta = build_anlamadim_prompt(
        "1.1",
        long_text,
        8,
        {"tema": "genel", "tarz": "kisa", "seviye": "orta", "mesaj": "Ana fikri ver."},
        return_meta=True,
    )

    assert meta["parca_sinifi"] == "uzun"
    assert meta["prompt_kisaltildi_mi"] is True
    assert meta["prompt_parca_metin_uzunlugu"] < meta["parca_metin_uzunlugu"]


def test_build_anlamadim_prompt_meta_code_parcasi_icin_ek_yorum_alanlari_ister():
    chunk = """def test_create_document(self):
    self.client.force_authenticate(user=self.author_user)
    response = self.client.post('/api/v1/documents/', data)
"""

    messages, meta = build_anlamadim_prompt(
        "code:python:code_block:2",
        chunk,
        11,
        {
            "tema": "genel",
            "tarz": "adim_adim",
            "seviye": "orta",
            "mesaj": "Bu testi acikla.",
            "chunk_kind": "code",
            "code_subtype": "api_test",
            "language": "python",
            "code_unit_kind": "test_function",
            "test_step_kind": "assertion",
            "line_start": 18,
            "line_end": 20,
        },
        return_meta=True,
    )

    prompt_text = "\n".join(item["content"] for item in messages)
    assert meta["istenen_alan_sayisi"] == 11
    assert "function_purpose" in prompt_text
    assert "flow_summary" in prompt_text
    assert "line_comments" in prompt_text
    assert "arrange/act/assert" in prompt_text.lower()
    assert "monkeypatch/mock satirlarini hazirlik adimi" in prompt_text.lower()
    assert "'kontrol eder', 'bir sey yapar', 'veriyi isler'" in prompt_text.lower()
    assert "code_unit_kind=test_function" in prompt_text.lower()
    assert "test_step_kind=assertion" in prompt_text.lower()
    assert "METIN:\ndef test_create_document(self):\n    self.client.force_authenticate" in prompt_text


def test_build_anlamadim_prompt_method_parcasi_icin_state_ve_helper_akisini_ister():
    chunk = """def add_item(self, item):
    prepared = normalize_item(item)
    self.items = self.items + [prepared]
    return len(self.items)
"""

    messages, meta = build_anlamadim_prompt(
        "code:python:code_block:3",
        chunk,
        12,
        {
            "tema": "genel",
            "tarz": "adim_adim",
            "seviye": "orta",
            "mesaj": "Bu methodu acikla.",
            "chunk_kind": "code",
            "code_subtype": "method",
            "language": "python",
            "code_unit_kind": "method",
            "line_start": 70,
            "line_end": 73,
        },
        return_meta=True,
    )

    prompt_text = "\n".join(item["content"] for item in messages)
    assert meta["istenen_alan_sayisi"] == 11
    assert "code_unit_kind=method" in prompt_text.lower()
    assert "helper call varsa" in prompt_text.lower()
    assert "state'ini okuma/guncelleme" in prompt_text.lower()
    assert "self.x = y" in prompt_text.lower()
    assert "satir araligi 70-73" in prompt_text.lower()


def test_build_anlamadim_prompt_mentions_non_python_heuristic_boundaries():
    sql_prompt = "\n".join(
        item["content"]
        for item in build_anlamadim_prompt(
            "code:sql:select:1",
            "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent",
            31,
            {"chunk_kind": "code", "code_subtype": "sql", "language": "sql"},
        )
    )
    config_prompt = "\n".join(
        item["content"]
        for item in build_anlamadim_prompt(
            "code:yaml:section:1",
            "defaults: &defaults\n  timeout: 30\nservice:\n  <<: *defaults",
            32,
            {"chunk_kind": "code", "code_subtype": "config", "language": "yaml"},
        )
    )
    markup_prompt = "\n".join(
        item["content"]
        for item in build_anlamadim_prompt(
            "code:html:markup:1",
            "<div>{{ item.title }}</div>",
            33,
            {"chunk_kind": "code", "code_subtype": "markup", "language": "html"},
        )
    )
    shell_prompt = "\n".join(
        item["content"]
        for item in build_anlamadim_prompt(
            "code:powershell:function:1",
            "Get-ChildItem | Where-Object { $_.Length -gt 1 }",
            34,
            {"chunk_kind": "code", "code_subtype": "shell", "language": "powershell"},
        )
    )

    assert "cte, subquery veya window function" in sql_prompt.lower()
    assert "anchor/alias" in config_prompt.lower()
    assert "template syntax" in markup_prompt.lower()
    assert "pipeline, subshell" in shell_prompt.lower()
    assert "gorunmeyen davranisi uydurma" in sql_prompt.lower()
