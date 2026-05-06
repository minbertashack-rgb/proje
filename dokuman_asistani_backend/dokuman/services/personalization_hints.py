from __future__ import annotations

from collections import Counter

from dokuman.models import MetrikKaydi

ALLOWED_TEMALAR = {"genel", "yazilim", "saglik", "matematik", "spor", "yemek", "oyun", "teknoloji", "film"}
ALLOWED_TONLAR = {"kanka", "hoca", "teknik", "sunum"}
ALLOWED_DETAY = {"dusuk", "orta", "yuksek"}
STYLE_MODLARI = {"kisa", "derin", "ornekli", "tablo", "akis"}
REMIX_MODLARI = {"hizli_cut", "story_cut", "exam_cut"}
EXCEL_MODLARI = {"tablo_anlatici", "formul_aciklayici", "filtrele_karsilastir_oneri", "grafik_ozeti"}


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_choice(value: str, *, allowed: set[str], default: str) -> str:
    clean = _clean_text(value).lower()
    return clean if clean in allowed else default


def _preference_ton(tercih) -> str:
    explicit = _safe_choice(getattr(tercih, "ton", ""), allowed=ALLOWED_TONLAR, default="")
    if explicit:
        return explicit
    fallback = _safe_choice(getattr(tercih, "tarz", ""), allowed=ALLOWED_TONLAR, default="")
    return fallback or "hoca"


def _preference_detay(tercih) -> str:
    explicit = _safe_choice(getattr(tercih, "detay_seviyesi", ""), allowed=ALLOWED_DETAY, default="")
    if explicit:
        return explicit
    seviye = _safe_choice(getattr(tercih, "seviye", ""), allowed={"baslangic", "orta", "ileri"}, default="orta")
    return {
        "baslangic": "dusuk",
        "orta": "orta",
        "ileri": "yuksek",
    }.get(seviye, "orta")


def _top_key(counter: Counter[str], default: str) -> str:
    if not counter:
        return default
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _metric_snapshot(*, user, enabled: bool) -> dict:
    snapshot = {
        "style_modlari": Counter(),
        "excel_modlari": Counter(),
        "remix_modlari": Counter(),
        "tonlar": Counter(),
        "olaylar": Counter(),
    }
    if not enabled:
        return snapshot

    kayitlar = MetrikKaydi.objects.filter(kullanici=user).order_by("-id")[:80]
    for kayit in kayitlar:
        olay = _clean_text(getattr(kayit, "olay_turu", "")).lower()
        if not olay:
            continue
        skor_ozeti = dict(getattr(kayit, "skor_ozeti", {}) or {})
        snapshot["olaylar"][olay] += 1

        ton = _safe_choice(skor_ozeti.get("ton"), allowed=ALLOWED_TONLAR, default="")
        if ton:
            snapshot["tonlar"][ton] += 1

        stil = _safe_choice(skor_ozeti.get("stil"), allowed=STYLE_MODLARI, default="")
        if stil:
            snapshot["style_modlari"][stil] += 1

        remix = _safe_choice(skor_ozeti.get("mod"), allowed=REMIX_MODLARI, default="")
        if olay == "directors_cut_uretildi" and remix:
            snapshot["remix_modlari"][remix] += 1

        excel_mod = _safe_choice(
            skor_ozeti.get("excel_mode") or skor_ozeti.get("mod"),
            allowed=EXCEL_MODLARI,
            default="",
        )
        if olay == "excel_mode_uretildi" and excel_mod:
            snapshot["excel_modlari"][excel_mod] += 1

    return snapshot


def _recommended_ton(*, tercih, snapshot: dict) -> str:
    adaylar = Counter({_preference_ton(tercih): 3})
    adaylar.update(snapshot.get("tonlar") or {})

    quiz_sayisi = int((snapshot.get("olaylar") or {}).get("mini_quiz_sonuclandi", 0))
    boss_sayisi = int((snapshot.get("olaylar") or {}).get("boss_deneme_tamamlandi", 0))
    self_check_sayisi = int((snapshot.get("olaylar") or {}).get("self_check_calistirildi", 0))
    confusion_sayisi = int((snapshot.get("olaylar") or {}).get("ai2_anlamadim_degerlendirildi", 0))

    if boss_sayisi + self_check_sayisi >= 2:
        adaylar["teknik"] += 2
    if confusion_sayisi >= max(2, quiz_sayisi):
        adaylar["hoca"] += 2
    if int((snapshot.get("remix_modlari") or {}).get("story_cut", 0)) >= 1:
        adaylar["sunum"] += 1
    return _top_key(adaylar, _preference_ton(tercih))


def _recommended_detay(*, tercih, snapshot: dict) -> str:
    adaylar = Counter({_preference_detay(tercih): 3})
    olaylar = snapshot.get("olaylar") or {}
    if int(olaylar.get("boss_deneme_tamamlandi", 0)) + int(olaylar.get("self_check_calistirildi", 0)) >= 2:
        adaylar["yuksek"] += 2
    if int(olaylar.get("ai2_anlamadim_degerlendirildi", 0)) >= 2 and int(olaylar.get("self_check_calistirildi", 0)) == 0:
        adaylar["dusuk"] += 2
    if int(olaylar.get("study_summary_uretildi", 0)) >= 2:
        adaylar["orta"] += 1
    if int((snapshot.get("style_modlari") or {}).get("derin", 0)) >= 1:
        adaylar["yuksek"] += 1
    return _top_key(adaylar, _preference_detay(tercih))


def _recommended_mode(*, tone: str, detay: str, snapshot: dict) -> str:
    olaylar = snapshot.get("olaylar") or {}
    if int(olaylar.get("ai2_anlamadim_degerlendirildi", 0)) >= 2 and int(olaylar.get("self_check_calistirildi", 0)) == 0:
        return "self_check"
    if snapshot.get("style_modlari"):
        return _top_key(snapshot["style_modlari"], "derin")
    if snapshot.get("remix_modlari"):
        return _top_key(snapshot["remix_modlari"], "exam_cut")
    if snapshot.get("excel_modlari"):
        return _top_key(snapshot["excel_modlari"], "tablo_anlatici")
    if tone == "sunum":
        return "story_cut"
    if detay == "yuksek":
        return "derin"
    if tone == "hoca":
        return "akis"
    return "ornekli"


def _reason_text(*, snapshot: dict, tone: str, detay: str, mode: str) -> str:
    sinyaller = ["tercih profili"]
    if snapshot.get("style_modlari") or snapshot.get("remix_modlari") or snapshot.get("excel_modlari"):
        sinyaller.append("kullanilan modlar")
    elif snapshot.get("tonlar"):
        sinyaller.append("style gecmisi")

    olaylar = snapshot.get("olaylar") or {}
    if (
        int(olaylar.get("study_summary_uretildi", 0))
        + int(olaylar.get("mini_quiz_sonuclandi", 0))
        + int(olaylar.get("self_check_calistirildi", 0))
        + int(olaylar.get("boss_deneme_tamamlandi", 0))
        + int(olaylar.get("ai2_anlamadim_degerlendirildi", 0))
    ) > 0:
        sinyaller.append("ogrenme paterni")

    prefix = " ve ".join(sinyaller[:2])
    return f"{prefix} daha {tone} tonda, {detay} detayda ve {mode} modunda daha tutarli gorunuyor."


def build_personalization_hints_payload(*, user, tercih, metric_store_enabled: bool = True) -> dict:
    snapshot = _metric_snapshot(user=user, enabled=metric_store_enabled)
    tema = _safe_choice(getattr(tercih, "tema", ""), allowed=ALLOWED_TEMALAR, default="genel")
    tone = _recommended_ton(tercih=tercih, snapshot=snapshot)
    detay = _recommended_detay(tercih=tercih, snapshot=snapshot)
    mod = _recommended_mode(tone=tone, detay=detay, snapshot=snapshot)

    return {
        "onerilen_tema": tema,
        "onerilen_ton": tone,
        "onerilen_detay_seviyesi": detay,
        "onerilen_mod": mod,
        "onerinin_gerekcesi_kisa": _reason_text(snapshot=snapshot, tone=tone, detay=detay, mode=mod),
    }
