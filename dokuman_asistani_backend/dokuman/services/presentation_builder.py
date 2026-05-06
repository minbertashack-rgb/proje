from __future__ import annotations

from dokuman.services.study_summary import build_study_summary_payload


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _bullets_from_section(section: dict) -> list[str]:
    bullets = [
        _clean_text(section.get("amaci")),
        _clean_text(section.get("konusma_notu")),
    ]
    source_ids = ", ".join(str(item) for item in (section.get("kaynak_parca_idleri") or [])[:4])
    if source_ids:
        bullets.append(f"Kaynak parcalar: {source_ids}")
    return [item for item in bullets if item]


def build_presentation_payload(*, doc, user, manifest: dict) -> dict:
    summary = build_study_summary_payload(doc=doc, user=user)
    section_slides = [
        {
            "title": _clean_text(section.get("baslik")) or "Bolum",
            "bullets": _bullets_from_section(section),
            "notes": (
                _clean_text(section.get("konusma_notu"))
                or f"Bu slaytin ana mesaji '{_clean_text(section.get('baslik')) or 'bolum'}' etrafinda netlesmeli; once amaci, sonra kaynak destegini acikla."
            ),
        }
        for section in list(manifest.get("bolumler") or [])[:4]
    ]
    slides = [
        {
            "title": doc.baslik or f"Dokuman {doc.id}",
            "bullets": [summary.get("kisa_ozet") or "Bu sunum manifest uzerinden uretildi."],
            "notes": "Bu sunumun amacini ve dokumanin neden onemli oldugunu tek cumlede acikla.",
        },
        {
            "title": "Hizli Ozet",
            "bullets": list(summary.get("ana_maddeler") or [])[:3],
            "notes": "Ana maddeleri tek tek saymak yerine ortak mesaji ve en kritik farki vurgula.",
        },
        {
            "title": "Kaynak Cekirdegi",
            "bullets": [
                f"Kaynak parca sayisi: {len(manifest.get('kaynak_parca_idleri') or [])}",
                f"Tahmini bolum sayisi: {manifest.get('tahmini_bolum_sayisi') or len(manifest.get('bolumler') or [])}",
            ],
            "notes": "Sunumun kapsam ve kaynak omurgasini sabitle; hangi parcadan hangi mesajin geldigini kisaca bagla.",
        },
    ]
    slides.extend(section_slides)
    slides.append(
        {
            "title": "Kapanis",
            "bullets": list(summary.get("kritik_notlar") or [])[:3] or ["Kritik not bulunamadi."],
            "notes": "Kapanista neden onemli, hangi risk var ve sonraki adim ne bunlari tek cercevede topla.",
        }
    )
    return {
        "dokuman_id": doc.id,
        "baslik": doc.baslik or f"Dokuman {doc.id}",
        "slaytlar": slides[:8],
        "kaynak_parca_idleri": list(manifest.get("kaynak_parca_idleri") or []),
    }
