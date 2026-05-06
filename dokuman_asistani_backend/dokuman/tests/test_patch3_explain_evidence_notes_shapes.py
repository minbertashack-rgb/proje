import json

import pytest
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from dokuman.models import AnlamadimKaydi, Dokuman, Not, Parca


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _doc_with_parca(user, *, title="Patch3 Doc", text="JWT access token kimlik tasir.", adres="1.1"):
    doc = Dokuman.objects.create(
        owner=user,
        baslik=title,
        mime="application/pdf",
        durum="parcalandi",
    )
    doc.dosya.save("patch3.pdf", ContentFile(b"ornek"), save=True)
    parca = Parca.objects.create(
        dokuman=doc,
        sira=1,
        tur="bolum",
        adres=adres,
        metin=text,
        meta={"path": adres, "baslik": title},
    )
    return doc, parca


@pytest.mark.django_db
def test_parca_anlamadim_v2_adds_client_contract_and_hides_internal_fields_without_debug(
    test_kullanicisi,
    monkeypatch,
    gecici_media_root,
):
    _, parca = _doc_with_parca(
        test_kullanicisi,
        title="JWT Explain",
        text="JWT access token kullanicinin kimligini tasir. Refresh token yeni access token alir.",
    )

    monkeypatch.setattr(
        "dokuman.views.chat",
        lambda messages, max_tokens=256: json.dumps(
            {
                "one_liner": "JWT kimlik tasima icin kullanilir.",
                "very_simple": "Access token kimligi tasir, refresh token yenileme icin vardir.",
                "glossary": [{"terim": "JWT", "aciklama": "Kimlik bilgisini tasiyan token."}],
                "steps": ["Access tokeni oku.", "Refresh tokenin yenileme rolunu ayir."],
                "examples": ["Bir oturum suresi dolunca refresh token devreye girer."],
                "trap": "Access ile refresh tokeni ayni sey sanma.",
                "mini_quiz": [],
                "dokumanda_yok": False,
            },
            ensure_ascii=False,
        ),
    )

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/parcalar/{parca.id}/anlamadim-v2/",
        {"mesaj": "Bunu sade anlat."},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["answer_state"] == "answered"
    assert response.data["status_text"] == "Aciklama hazir."
    assert response.data["warning_code"] == ""
    assert response.data["answer_allowed"] is True
    assert response.data["weak_evidence"] is False
    assert response.data["evidence_strength"] == "yuksek"
    assert response.data["abstain_reason"] == ""
    assert response.data["kaynak_guveni"] == "yuksek"
    assert "view_marker" not in response.data
    assert "debug_ai2" not in response.data
    assert "kayit_hata" not in response.data


@pytest.mark.django_db
def test_ai2_kanitli_cevap_adds_decision_fields(
    test_kullanicisi,
    monkeypatch,
    gecici_media_root,
):
    doc, _ = _doc_with_parca(
        test_kullanicisi,
        title="AI2 Evidence",
        text="RAG once ilgili parcayi bulur sonra cevap icin kanit kullanir.",
        adres="RAG > Giris",
    )
    second = Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="RAG > Kaynak",
        metin="Kaynakli cevapta parca_id izlenebilirligi hangi kanitin kullanildigini gosterir.",
        meta={"path": "RAG > Kaynak"},
    )

    monkeypatch.setattr(
        "dokuman.views_ai2.chat",
        lambda messages, max_tokens=256: (
            '{"answer":"Parca kimligini gostermek hangi kanitin kullanildigini izlenebilir kilar.",'
            f'"supported":true,"citations":[{second.id}],"missing":[],"followups":[]}}'
        ),
    )

    response = _client(test_kullanicisi).post(
        "/api/dokuman-asistani/ai2/kanitli-cevap/",
        {"question": "Hangi kanitin kullanildigini ne gosterir?", "doc_id": doc.id, "top_k": 2},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["dokumanda_yok"] is False
    assert response.data["answer_allowed"] is True
    assert response.data["answer_state"] == "answered"
    assert response.data["status_text"] == "Kanitli cevap hazir."
    assert response.data["warning_code"] == ""
    assert response.data["kaynak_guveni"] in {"orta", "yuksek"}
    assert response.data["evidence_strength"] in {"orta", "yuksek"}


@pytest.mark.django_db
def test_legacy_kanitli_sor_adds_decision_fields(
    test_kullanicisi,
    monkeypatch,
    gecici_media_root,
):
    doc, _ = _doc_with_parca(
        test_kullanicisi,
        title="Legacy QA",
        text="RAG once ilgili parcayi bulur ve sonra cevap icin kanit kullanir.",
        adres="Legacy > Giris",
    )
    Parca.objects.create(
        dokuman=doc,
        sira=2,
        tur="bolum",
        adres="Legacy > Kaynak",
        metin="Parca kimligi cevap ile kanit arasindaki bagi gorunur kilar.",
        meta={"path": "Legacy > Kaynak"},
    )

    monkeypatch.setattr("dokuman.views.yerel_modeli_al", lambda: None)

    response = _client(test_kullanicisi).post(
        f"/api/dokuman-asistani/dokumanlar/{doc.id}/sor/",
        {"soru": "Parca kimligi neden onemli?"},
        format="json",
    )

    assert response.status_code == 200
    assert "answer_state" in response.data
    assert "status_text" in response.data
    assert "warning_code" in response.data
    assert "dokumanda_yok" in response.data
    assert "answer_allowed" in response.data
    assert "weak_evidence" in response.data
    assert "evidence_strength" in response.data
    assert "abstain_reason" in response.data
    assert "kaynak_guveni" in response.data


@pytest.mark.django_db
def test_not_create_and_missing_note_follow_patch2_style(test_kullanicisi, django_user_model, gecici_media_root):
    client = _client(test_kullanicisi)

    invalid_response = client.post(
        "/api/dokuman-asistani/notlar/",
        {"baslik": "Bos"},
        format="json",
    )

    assert invalid_response.status_code == 400
    assert invalid_response.data["error_code"] == "validation_error"
    assert invalid_response.data["status_text"] == invalid_response.data["detail"]
    assert invalid_response.data["field_errors"]["metin"] == ["Bu alan zorunludur."]

    other = django_user_model.objects.create_user(username="patch3_other", password="12345678")
    note = Not.objects.create(owner=other, baslik="Gizli", metin="Baska kullanici notu", not_turu="serbest")

    missing_response = client.get(f"/api/dokuman-asistani/notlar/{note.id}/")

    assert missing_response.status_code == 404
    assert missing_response.data["error_code"] == "resource_not_found"
    assert missing_response.data["status_text"] == missing_response.data["detail"]


@pytest.mark.django_db
def test_notes_success_and_history_envelope_add_status_text(test_kullanicisi, gecici_media_root):
    doc, parca = _doc_with_parca(test_kullanicisi, title="Notes History")
    client = _client(test_kullanicisi)

    note_response = client.post(
        "/api/dokuman-asistani/notlar/",
        {
            "dokuman": doc.id,
            "parca": parca.id,
            "baslik": "JWT notu",
            "metin": "Access ve refresh token farki.",
        },
        format="json",
    )

    assert note_response.status_code == 201
    assert note_response.data["status_text"] == "Not kaydedildi."
    assert note_response.data["warning_code"] == ""

    AnlamadimKaydi.objects.create(
        kullanici=test_kullanicisi,
        dokuman=doc,
        parca=parca,
        adres=parca.adres,
        kullanici_mesaj="JWT secimi",
        cikti_text="Bu kisim zor geldi",
    )

    history_response = client.get("/api/dokuman-asistani/anlamadim/")

    assert history_response.status_code == 200
    assert history_response.data["durum"] == "ok"
    assert history_response.data["status_text"] == "Gecmis kayitlar hazir."
    assert history_response.data["adet"] >= 1
