from __future__ import annotations

from dokuman.services.study_summary import build_study_summary_payload

ALLOWED_MODLAR = {
    "tablo_anlatici",
    "formul_aciklayici",
    "filtrele_karsilastir_oneri",
    "grafik_ozeti",
}


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_mod(value: str) -> str:
    clean = _clean_text(value).lower()
    return clean if clean in ALLOWED_MODLAR else "tablo_anlatici"


def _safe_int(value, default: int = 0) -> int:
    try:
        return max(int(value), 0)
    except Exception:
        return default


def _table_contexts(doc, preferred_ids: list[int]) -> list[dict]:
    ordered = []
    seen = set()
    for parca in doc.parcalar.filter(id__in=preferred_ids).order_by("id"):
        seen.add(parca.id)
        ordered.append(parca)

    for parca in doc.parcalar.order_by("id"):
        if parca.id in seen:
            continue
        ordered.append(parca)

    contexts = []
    for parca in ordered:
        meta = dict(getattr(parca, "meta", {}) or {})
        is_table_like = (
            parca.tur in {"tablo", "table", "excel"}
            or bool(meta.get("is_table"))
            or any(
                key in meta
                for key in (
                    "row_count",
                    "rows",
                    "column_count",
                    "columns",
                    "formula_count",
                    "formula_cells",
                    "chart_count",
                    "charts",
                    "sheet",
                )
            )
        )
        if not is_table_like:
            continue

        contexts.append(
            {
                "parca_id": parca.id,
                "tur": _clean_text(parca.tur).lower() or "tablo",
                "sheet": _clean_text(meta.get("sheet") or meta.get("sheet_name")),
                "adres": _clean_text(getattr(parca, "adres", "")),
                "satir": _safe_int(meta.get("row_count") or meta.get("rows"), 0),
                "sutun": _safe_int(meta.get("column_count") or meta.get("columns"), 0),
                "formul": _safe_int(meta.get("formula_count") or meta.get("formula_cells"), 0),
                "grafik": _safe_int(meta.get("chart_count") or meta.get("charts"), 0) + (1 if meta.get("chart_type") else 0),
                "zorluk_skoru": float(getattr(parca, "zorluk_skoru", 0.0) or 0.0),
            }
        )
        if len(contexts) >= 8:
            break
    return contexts


def _sheet_count(contexts: list[dict]) -> int:
    values = {item["sheet"] for item in contexts if item.get("sheet")}
    return len(values) or (1 if contexts else 0)


def _kaynak_ids(contexts: list[dict]) -> list[int]:
    return [item["parca_id"] for item in contexts][:12]


def _table_story_line(*, tablo_sayisi: int, sheet_sayisi: int, ortalama_satir: float, ortalama_sutun: float) -> str:
    return (
        f"Tablo ne gosteriyor: {sheet_sayisi} sheet uzerine yayilan {tablo_sayisi} yapisal blok var; "
        f"veri mantigi ortalama {ortalama_satir} satir ve {ortalama_sutun} sutunluk omurga ile okunmali."
    )


def _reason_payload(mod: str, doc, portal_not, reason: str) -> dict:
    return {
        "dokuman_id": doc.id,
        "portal_not_id": getattr(portal_not, "id", None),
        "mod": mod,
        "baslik": f"{doc.baslik or f'Dokuman {doc.id}'} Excel Modu",
        "kartlar": [
            {"etiket": "tablo_sayisi", "deger": 0},
            {"etiket": "sheet_sayisi", "deger": 0},
            {"etiket": "reason", "deger": reason},
        ],
        "oneriler": [
            "Tablo veya sheet metadata'si bulunamadi; once yapisal excel parcasi olusmasi gerekiyor.",
        ],
        "kaynak_parca_idleri": [],
        "_meta": {
            "excel_mode": mod,
            "supported": False,
            "unsupported_reason": reason,
            "bagli_parca_sayisi": 0,
        },
    }


def build_excel_mode_payload(*, doc, user, mod: str = "tablo_anlatici", portal_not=None) -> dict:
    mod = _normalize_mod(mod)
    summary = build_study_summary_payload(doc=doc, user=user, portal_not=portal_not)
    contexts = _table_contexts(doc, list(summary.get("bagli_parca_idleri") or []))

    if not contexts:
        return _reason_payload(mod, doc, portal_not, "table_data_missing")

    kaynak_ids = _kaynak_ids(contexts)
    tablo_sayisi = len(contexts)
    sheet_sayisi = _sheet_count(contexts)
    toplam_satir = sum(item["satir"] for item in contexts)
    toplam_sutun = sum(item["sutun"] for item in contexts)
    toplam_formul = sum(item["formul"] for item in contexts)
    toplam_grafik = sum(item["grafik"] for item in contexts)
    ortalama_satir = round(toplam_satir / max(tablo_sayisi, 1), 1)
    ortalama_sutun = round(toplam_sutun / max(tablo_sayisi, 1), 1)
    yuksek_oncelik = sum(1 for item in contexts if float(item["zorluk_skoru"]) >= 0.6)

    if mod == "tablo_anlatici":
        kartlar = [
            {"etiket": "tablo_sayisi", "deger": tablo_sayisi},
            {"etiket": "sheet_sayisi", "deger": sheet_sayisi},
            {"etiket": "ortalama_satir_tahmini", "deger": ortalama_satir},
        ]
        oneriler = [
            _table_story_line(
                tablo_sayisi=tablo_sayisi,
                sheet_sayisi=sheet_sayisi,
                ortalama_satir=ortalama_satir,
                ortalama_sutun=ortalama_sutun,
            ),
            f"Onemli sutun mantigi: kolon omurgasi yaklasik {ortalama_sutun} sutun; kimlik, olcu ve sonuc kolonlari ayri okunmali.",
            f"Dikkat ceken iliski: kaynak bloklar {len(kaynak_ids)} parca ile sinirli; yuksek oncelikli {yuksek_oncelik} blok veri hikayesini tasiyor olabilir.",
        ]
    elif mod == "formul_aciklayici":
        formul_tasiyan = sum(1 for item in contexts if item["formul"] > 0)
        kartlar = [
            {"etiket": "formul_hucresi_tahmini", "deger": toplam_formul},
            {"etiket": "formul_iceren_tablo_sayisi", "deger": formul_tasiyan},
            {"etiket": "hesaplama_kapsami", "deger": min(tablo_sayisi, max(1, formul_tasiyan))},
        ]
        oneriler = [
            f"Excel verisinin mantigi: yaklasik {toplam_formul} hucre hesaplama yapiyor; once sonucu degistiren formul kolonlari okunmali.",
            f"Formul tasiyan {formul_tasiyan} tablo parcasi icin once hesap sonucu, sonra bu sonucu besleyen kolon-satir zinciri anlatilmali.",
            f"Dogrulama notu: kaynak inceleme {len(kaynak_ids)} parca ile sinirli tutulup kolon-satir baglantisi ayrica kontrol edilmeli.",
        ]
    elif mod == "filtrele_karsilastir_oneri":
        filtrelenebilir = sum(1 for item in contexts if item["sutun"] >= 3)
        kartlar = [
            {"etiket": "karsilastirma_adayi_blok_sayisi", "deger": tablo_sayisi},
            {"etiket": "filtrelenebilir_blok_sayisi", "deger": filtrelenebilir},
            {"etiket": "yuksek_oncelik_blok_sayisi", "deger": yuksek_oncelik},
        ]
        oneriler = [
            f"Veri ne anlatiyor: {filtrelenebilir} blok coklu kolon yapisi tasiyor; filtre mantigi bu bloklardan baslayinca ana farklar daha net gorunur.",
            f"Karsilastirma mantigi: toplam {tablo_sayisi} tablo parcasi cekirdek ve istisna gruplarina ayrilarak okunursa sapmalar daha kolay yakalanir.",
            f"Dikkat ceken iliski: yuksek zorluklu {yuksek_oncelik} blok icin ayri bir karsilastirma listesi tutmak daha guvenli olur.",
        ]
    else:
        grafik_adayi = max(toplam_grafik, 1 if toplam_satir and tablo_sayisi else 0)
        trend_adayi = sum(1 for item in contexts if item["satir"] >= 8 and item["sutun"] >= 2)
        kartlar = [
            {"etiket": "grafik_adayi_sayisi", "deger": grafik_adayi},
            {"etiket": "trend_blok_sayisi", "deger": trend_adayi},
            {"etiket": "sunuma_hazir_blok_sayisi", "deger": min(trend_adayi or tablo_sayisi, 2)},
        ]
        oneriler = [
            f"Grafik ne anlatiyor: {grafik_adayi} aday sinyal ve {trend_adayi} trend blok var; once degisim sonra karsilastirma okunmali.",
            f"Veri hikayesi: toplam {toplam_satir} satirlik yogunluk trend cikarmaya uygun; grafik anlatiminda eksen mantigi once aciklanmali.",
            f"Sunuma hazir blok secimi {len(kaynak_ids)} kaynak parcadan en fazla iki cekirdek blok ile sinirlanirsa mesaj daha net kalir.",
        ]

    return {
        "dokuman_id": doc.id,
        "portal_not_id": getattr(portal_not, "id", None),
        "mod": mod,
        "baslik": f"{doc.baslik or f'Dokuman {doc.id}'} Excel Modu",
        "kartlar": kartlar,
        "oneriler": oneriler,
        "kaynak_parca_idleri": kaynak_ids,
        "_meta": {
            "excel_mode": mod,
            "supported": True,
            "bagli_parca_sayisi": len(kaynak_ids),
            "kullanilan_parca_sayisi": len(kaynak_ids),
            "unsupported_reason": "",
        },
    }
