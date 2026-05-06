import io
import re
from collections import Counter
from pathlib import Path

try:
    import pytesseract
except Exception:
    pytesseract = None
from PIL import Image, ImageOps, ImageFilter, UnidentifiedImageError
from django.conf import settings

from dokuman.models import Parca
from dokuman.services.metric_store import kaydet_skor_olayi
from dokuman.services.phase2_scores import analyze_cheatsheet_priority
from .ingestion_contract import (
    ingestion_bulkunu_kaydet,
    ingestion_sonucunu_kaydet,
)
from .ingestion import _difficulty_score_analizi, _quality_score_analizi


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
_OCR_VALID_CHAR_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9\s\.,;:!?\-\+\(\)\[\]/%&=_#'\"“”‘’]+", re.UNICODE)
_OCR_TOKEN_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]+", re.UNICODE)
_OCR_ALPHA_TOKEN_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", re.UNICODE)


def is_image_ext(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_EXTS


def _configure_tesseract():
    if pytesseract is None:
        raise RuntimeError("pytesseract kurulu degil.")
    cmd = getattr(settings, "TESSERACT_CMD", "") or ""
    cmd = cmd.strip()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def _ocr_strict_quality_mode_enabled() -> bool:
    return bool(getattr(settings, "DOCVERSE_OCR_STRICT_QUALITY_MODE", False))


def _preprocess_image(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    img = img.convert("L")
    img = ImageOps.autocontrast(img)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.point(lambda p: 255 if p > 170 else 0)
    return img


def normalize_ocr_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(line)

    cleaned = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False

    return "\n".join(cleaned).strip()


def _ocr_confidence_band(score: float) -> str:
    clean_score = max(0.0, min(float(score or 0.0), 1.0))
    if clean_score >= 0.72:
        return "yuksek"
    if clean_score >= 0.48:
        return "orta"
    return "dusuk"


def _ocr_warning(quality_meta: dict) -> str:
    if not quality_meta:
        return ""
    if str(quality_meta.get("ocr_quality_reason") or "").strip() == "empty_ocr":
        return "low_quality_ocr"
    if float(quality_meta.get("ocr_garbage_ratio") or 0.0) >= 0.30:
        return "low_quality_ocr"
    if float(quality_meta.get("ocr_symbol_noise_ratio") or 0.0) >= 0.22:
        return "symbol_noise"
    if float(quality_meta.get("ocr_single_char_token_ratio") or 0.0) >= 0.34:
        return "single_char_fragmentation"
    if float(quality_meta.get("ocr_broken_line_ratio") or 0.0) >= 0.45:
        return "broken_lines"
    if float(quality_meta.get("ocr_upper_cluster_ratio") or 0.0) >= 0.72:
        return "upper_cluster_noise"
    if float(quality_meta.get("ocr_column_noise_ratio") or 0.0) >= 0.45:
        return "column_noise"
    if str(quality_meta.get("ocr_confidence_band") or "").strip() == "dusuk":
        return "low_quality_ocr"
    return ""


def _build_ocr_signal_meta(*, kaynak_turu: str, ocr_quality_meta: dict) -> dict:
    return {
        "ocr_kullanildi": True,
        "ocr_kaynak_turu": str(kaynak_turu or "").strip(),
        "ocr_quality_score": float(ocr_quality_meta.get("ocr_quality_score") or 0.0),
        "ocr_confidence_band": str(ocr_quality_meta.get("ocr_confidence_band") or "dusuk").strip() or "dusuk",
        "ocr_warning": str(ocr_quality_meta.get("ocr_warning") or "").strip(),
    }


def analyze_ocr_quality(text: str) -> dict:
    clean = normalize_ocr_text(text)
    if not clean:
        score = 0.0
        return {
            "ocr_quality_score": score,
            "ocr_quality_reason": "empty_ocr",
            "ocr_alnum_density": 0.0,
            "ocr_garbage_ratio": 1.0,
            "ocr_symbol_noise_ratio": 1.0,
            "ocr_single_char_token_ratio": 1.0,
            "ocr_broken_line_ratio": 1.0,
            "ocr_upper_cluster_ratio": 1.0,
            "ocr_column_noise_ratio": 1.0,
            "ocr_short_meaningful": False,
            "ocr_confidence_band": _ocr_confidence_band(score),
            "ocr_warning": "low_quality_ocr",
            "weak_content": True,
            "gate_ok": False,
        }

    total_len = max(len(clean), 1)
    lines = [line.strip() for line in clean.split("\n") if line.strip()]
    tokens = _OCR_TOKEN_RE.findall(clean)
    alpha_tokens = _OCR_ALPHA_TOKEN_RE.findall(clean)
    alpha_words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]{2,}", clean)
    token_count = len(tokens)
    alnum_count = len(re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]", clean))
    invalid_count = sum(1 for ch in clean if not _OCR_VALID_CHAR_RE.fullmatch(ch))
    symbol_count = len(re.findall(r"[^A-Za-zÇĞİÖŞÜçğıöşü0-9\s]", clean))
    single_char_token_count = sum(1 for token in tokens if len(token) == 1 and token.isalpha())
    upper_cluster_count = sum(1 for token in alpha_tokens if len(token) >= 2 and token.isupper())

    broken_line_hits = 0
    column_noise_hits = 0
    for line in lines:
        line_tokens = _OCR_TOKEN_RE.findall(line)
        if not line_tokens:
            continue
        fragmented_tokens = sum(1 for token in line_tokens if len(token) == 1 and token.isalpha())
        short_token_count = sum(1 for token in line_tokens if len(token) <= 3)
        numeric_token_count = sum(1 for token in line_tokens if any(ch.isdigit() for ch in token))
        if (
            (len(line_tokens) == 1 and len(line) <= 18)
            or line.endswith("-")
            or fragmented_tokens >= max(2, len(line_tokens) // 2)
        ):
            broken_line_hits += 1
        if (
            len(line_tokens) >= 4
            and (short_token_count / max(len(line_tokens), 1)) >= 0.6
            and (numeric_token_count >= 1 or len({token.lower() for token in line_tokens}) >= 4)
        ):
            column_noise_hits += 1

    alnum_density = alnum_count / total_len
    garbage_ratio = invalid_count / total_len
    symbol_noise_ratio = symbol_count / total_len
    single_char_token_ratio = single_char_token_count / max(token_count, 1)
    broken_line_ratio = broken_line_hits / max(len(lines), 1) if len(lines) >= 2 else 0.0
    upper_cluster_ratio = upper_cluster_count / max(len(alpha_tokens), 1) if alpha_tokens else 0.0
    column_noise_ratio = column_noise_hits / max(len(lines), 1) if lines else 0.0
    short_meaningful = bool(
        len(clean) >= 4
        and len(clean) <= 24
        and len(alpha_words) >= 1
        and alnum_density >= 0.55
        and garbage_ratio <= 0.12
        and symbol_noise_ratio <= 0.18
        and single_char_token_ratio <= 0.34
    )

    score = (
        0.40 * alnum_density
        + 0.18 * min(token_count / 8.0, 1.0)
        + 0.16 * min(len(alpha_words) / 4.0, 1.0)
        + 0.14 * (1.0 - min(garbage_ratio * 3.0, 1.0))
        + 0.12 * (1.0 - min(symbol_noise_ratio * 2.5, 1.0))
    )
    score -= 0.24 * single_char_token_ratio
    score -= 0.18 * broken_line_ratio
    score -= 0.16 * upper_cluster_ratio
    score -= 0.18 * column_noise_ratio
    if token_count == 0:
        score = min(score, 0.12)
    if len(clean) < 8 and not short_meaningful:
        score *= 0.35
    if garbage_ratio >= 0.30:
        score *= 0.40
    if symbol_noise_ratio >= 0.22:
        score *= 0.65
    if token_count <= 1 and not short_meaningful:
        score = min(score, 0.18)
    if short_meaningful and score < 0.42:
        score = 0.42

    score = round(max(0.0, min(score, 1.0)), 3)
    confidence_band = _ocr_confidence_band(score)
    reason = "ocr_contentful"
    if garbage_ratio >= 0.30:
        reason = "ocr_garbage_heavy"
    elif symbol_noise_ratio >= 0.22:
        reason = "ocr_symbol_noise"
    elif single_char_token_ratio >= 0.34:
        reason = "ocr_fragmented_tokens"
    elif broken_line_ratio >= 0.45:
        reason = "ocr_broken_lines"
    elif upper_cluster_ratio >= 0.72:
        reason = "ocr_upper_cluster_noise"
    elif column_noise_ratio >= 0.45:
        reason = "ocr_column_noise"
    elif short_meaningful:
        reason = "ocr_short_meaningful"
    elif token_count <= 1:
        reason = "ocr_thin_content"

    quality_meta = {
        "ocr_quality_score": score,
        "ocr_quality_reason": reason,
        "ocr_alnum_density": round(alnum_density, 3),
        "ocr_garbage_ratio": round(garbage_ratio, 3),
        "ocr_symbol_noise_ratio": round(symbol_noise_ratio, 3),
        "ocr_single_char_token_ratio": round(single_char_token_ratio, 3),
        "ocr_broken_line_ratio": round(broken_line_ratio, 3),
        "ocr_upper_cluster_ratio": round(upper_cluster_ratio, 3),
        "ocr_column_noise_ratio": round(column_noise_ratio, 3),
        "ocr_short_meaningful": short_meaningful,
        "ocr_confidence_band": confidence_band,
    }
    warning = _ocr_warning(quality_meta)

    return {
        **quality_meta,
        "ocr_warning": warning,
        "weak_content": bool(
            score < 0.42
            or warning in {"single_char_fragmentation", "broken_lines", "upper_cluster_noise", "column_noise", "symbol_noise", "low_quality_ocr"}
        ),
        "gate_ok": bool(
            short_meaningful
            or (
                score >= 0.50
                and warning not in {"single_char_fragmentation", "broken_lines", "upper_cluster_noise", "column_noise", "symbol_noise"}
            )
        ),
    }


def extract_text_from_pil_image(img: Image.Image) -> str:
    _configure_tesseract()

    lang = getattr(settings, "OCR_LANG", "tur+eng")
    psm = int(getattr(settings, "OCR_PSM", 6))
    oem = int(getattr(settings, "OCR_OEM", 3))

    processed = _preprocess_image(img)
    text = pytesseract.image_to_string(
        processed,
        lang=lang,
        config=f"--oem {oem} --psm {psm}",
    )
    return normalize_ocr_text(text)


def extract_text_from_image(image_path: str) -> str:
    with Image.open(image_path) as img:
        return extract_text_from_pil_image(img.copy())


def extract_text_from_pdf_pages(pdf_path: str) -> list[dict]:
    import fitz  # pymupdf

    dpi = int(getattr(settings, "OCR_PDF_DPI", 180) or 180)
    scale = max(float(dpi) / 72.0, 1.0)
    page_rows = []
    doc = fitz.open(pdf_path)
    try:
        for page_no, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image_bytes = pix.tobytes("png")
            with Image.open(io.BytesIO(image_bytes)) as img:
                text = extract_text_from_pil_image(img.copy())
            page_rows.append(
                {
                    "page": page_no,
                    "text": text,
                    "image_width": int(getattr(pix, "width", 0) or 0),
                    "image_height": int(getattr(pix, "height", 0) or 0),
                }
            )
    finally:
        doc.close()
    return page_rows


def split_text_into_chunks(text: str, max_chars: int = 1200) -> list[str]:
    text = normalize_ocr_text(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks = []
    current = ""

    for para in paragraphs:
        if len(para) <= max_chars:
            candidate = f"{current}\n\n{para}".strip() if current else para
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = para
            continue

        words = para.split()
        temp = ""

        for word in words:
            candidate = f"{temp} {word}".strip()
            if len(candidate) <= max_chars:
                temp = candidate
            else:
                if temp:
                    if current:
                        chunks.append(current)
                        current = ""
                    chunks.append(temp)
                temp = word

        if temp:
            if not current:
                current = temp
            else:
                candidate = f"{current}\n\n{temp}".strip()
                if len(candidate) <= max_chars:
                    current = candidate
                else:
                    chunks.append(current)
                    current = temp

    if current:
        chunks.append(current)

    return chunks


def _parca_text_field_name() -> str:
    field_names = {f.name for f in Parca._meta.fields}
    for candidate in ["icerik", "metin", "text", "content"]:
        if candidate in field_names:
            return candidate
    raise RuntimeError(
        f"Parca modelinde metin alanı bulunamadı. Mevcut alanlar: {sorted(field_names)}"
    )


def _parca_order_field_name() -> str | None:
    field_names = {f.name for f in Parca._meta.fields}
    for candidate in ["sira", "sira_no", "sira_numarasi", "order", "index"]:
        if candidate in field_names:
            return candidate
    return None


def _image_mime_from_ext(ext: str) -> str:
    ext = ext.lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    if ext == ".bmp":
        return "image/bmp"
    if ext in {".tif", ".tiff"}:
        return "image/tiff"
    return "image/*"


def _detect_image_mime(image_path: str, ext: str) -> str:
    try:
        with Image.open(image_path) as img:
            detected = str(Image.MIME.get(str(getattr(img, "format", "") or "").upper()) or "").strip()
            return detected or _image_mime_from_ext(ext)
    except UnidentifiedImageError as exc:
        raise RuntimeError("Gorsel dosyasi okunamadi veya desteklenen bir raster format degil.") from exc
    except Exception:
        return _image_mime_from_ext(ext)


def _ocr_chunk_is_acceptable(
    *,
    chunk: str,
    base_quality_meta: dict,
    ocr_quality_meta: dict,
    combined_quality_score: float,
) -> bool:
    clean = normalize_ocr_text(chunk)
    if not clean:
        return False
    warning = str(ocr_quality_meta.get("ocr_warning") or "").strip()
    confidence_band = str(
        ocr_quality_meta.get("ocr_confidence_band")
        or _ocr_confidence_band(ocr_quality_meta.get("ocr_quality_score") or 0.0)
    ).strip()
    severe_warning = warning in {
        "single_char_fragmentation",
        "broken_lines",
        "upper_cluster_noise",
        "column_noise",
        "symbol_noise",
        "low_quality_ocr",
    }
    if (
        bool(ocr_quality_meta.get("ocr_short_meaningful"))
        and float(ocr_quality_meta.get("ocr_quality_score") or 0.0) >= 0.68
        and warning == ""
        and combined_quality_score >= 0.30
    ):
        return True
    if (
        bool(ocr_quality_meta.get("ocr_short_meaningful"))
        and bool(base_quality_meta.get("short_valid"))
        and warning == "column_noise"
        and float(ocr_quality_meta.get("ocr_quality_score") or 0.0) >= 0.55
        and combined_quality_score >= 0.48
    ):
        return True
    if severe_warning and combined_quality_score < 0.64:
        return False
    if confidence_band == "yuksek" and combined_quality_score >= 0.46:
        return True
    if bool(ocr_quality_meta.get("gate_ok")) and combined_quality_score >= 0.46:
        return True
    if bool(base_quality_meta.get("short_valid")) and combined_quality_score >= 0.42:
        return True
    if combined_quality_score >= 0.56 and not (
        bool(base_quality_meta.get("weak_content")) and bool(ocr_quality_meta.get("weak_content"))
    ):
        return True
    return False


def _ocr_chunk_aggregate(bulk, quality_rows) -> dict:
    accepted_rows = [item for item in (quality_rows or []) if bool(item.get("accepted"))]
    active_rows = accepted_rows or list(quality_rows or [])
    aggregate_ocr_quality = round(
        sum(float(item.get("ocr_quality_score") or 0.0) for item in active_rows) / max(len(active_rows), 1),
        3,
    ) if active_rows else 0.0
    warnings = [str(item.get("ocr_warning") or "").strip() for item in active_rows if str(item.get("ocr_warning") or "").strip()]
    aggregate_warning = ""
    if accepted_rows and len(accepted_rows) < len(quality_rows or []):
        aggregate_warning = "mixed_ocr_quality"
    elif warnings:
        aggregate_warning = Counter(warnings).most_common(1)[0][0]
    return {
        "quality_score": round(
            sum(float((p.meta or {}).get("quality_score") or 0.0) for p in bulk) / max(len(bulk), 1),
            3,
        ) if bulk else 0.0,
        "ocr_quality_score": aggregate_ocr_quality,
        "difficulty_score": round(
            sum(float((p.meta or {}).get("difficulty_score") or 0.0) for p in bulk) / max(len(bulk), 1),
            3,
        ) if bulk else 0.0,
        "weak_content": all(bool(item["weak_content"]) for item in quality_rows) if quality_rows else True,
        "ocr_confidence_band": _ocr_confidence_band(aggregate_ocr_quality),
        "ocr_warning": aggregate_warning,
        "accepted_chunk_sayisi": sum(1 for item in quality_rows if bool(item.get("accepted"))),
        "rejected_chunk_sayisi": sum(1 for item in quality_rows if not bool(item.get("accepted"))),
        "chunk_sayisi": len(bulk),
    }


def _save_ocr_failure(doc, *, kaynak_turu: str, mime: str, hata_mesaji: str, debug_ozeti: dict | None = None):
    ingestion_sonucunu_kaydet(
        doc,
        kaynak_turu=kaynak_turu,
        mime=mime,
        aday_parca_sayisi=0,
        kaydedilen_parca_sayisi=0,
        kalite_durumu="hata",
        hata_mesaji=hata_mesaji,
        debug_ozeti=debug_ozeti,
    )
    return doc


def gorseli_ocr_ile_parcala_ve_kaydet(doc):
    if not getattr(settings, "OCR_ENABLED", True):
        raise RuntimeError("OCR_ENABLED False olduğu için OCR kapalı.")

    file_path = getattr(getattr(doc, "dosya", None), "path", None)
    if not file_path:
        raise RuntimeError("Doküman dosya yolu alınamadı.")

    ext = Path(file_path).suffix.lower()
    if ext not in IMAGE_EXTS:
        raise RuntimeError(f"Desteklenmeyen görsel uzantısı: {ext}")
    mime = _detect_image_mime(file_path, ext)

    text = extract_text_from_image(file_path)
    if not text.strip():
        return _save_ocr_failure(
            doc,
            kaynak_turu="ocr",
            mime=mime,
            hata_mesaji="OCR metin cikaramadi.",
        )

    chunk_size = int(getattr(settings, "OCR_CHUNK_SIZE", 1200))
    chunks = split_text_into_chunks(text, max_chars=chunk_size)

    if not chunks:
        return _save_ocr_failure(
            doc,
            kaynak_turu="ocr",
            mime=_image_mime_from_ext(ext),
            hata_mesaji="OCR sonrasi parca uretilemedi.",
        )

    text_field = _parca_text_field_name()
    order_field = _parca_order_field_name()

    bulk = []
    quality_rows = []
    rejected_chunks = 0
    for i, chunk in enumerate(chunks, start=1):
        chunk = (chunk or "").strip()
        if not chunk:
            continue

        adres = f"ocr:{i}"
        base_quality_meta = _quality_score_analizi(
            chunk,
            icerik_uzunlugu=len(chunk),
            ocr=True,
        )
        ocr_quality_meta = analyze_ocr_quality(chunk)
        difficulty_meta = _difficulty_score_analizi(chunk, ocr=True)
        cheatsheet_meta = analyze_cheatsheet_priority(chunk)
        combined_quality_score = round(
            min(
                1.0,
                (0.7 * float(base_quality_meta["quality_score"]))
                + (0.3 * float(ocr_quality_meta["ocr_quality_score"])),
            ),
            3,
        )
        weak_content = bool(
            base_quality_meta["weak_content"] or ocr_quality_meta["weak_content"]
        )
        quality_rows.append(
            {
                "quality_score": combined_quality_score,
                "ocr_quality_score": ocr_quality_meta["ocr_quality_score"],
                "difficulty_score": difficulty_meta["difficulty_score"],
                "weak_content": weak_content,
                "ocr_confidence_band": ocr_quality_meta["ocr_confidence_band"],
                "ocr_warning": ocr_quality_meta["ocr_warning"],
                "accepted": False,
            }
        )
        accepted = _ocr_chunk_is_acceptable(
            chunk=chunk,
            base_quality_meta=base_quality_meta,
            ocr_quality_meta=ocr_quality_meta,
            combined_quality_score=combined_quality_score,
        )
        if _ocr_strict_quality_mode_enabled() and combined_quality_score < 0.62:
            accepted = False
        quality_rows[-1]["accepted"] = accepted
        if not accepted:
            rejected_chunks += 1
            continue
        kwargs = {
            "dokuman": doc,
            "tur": "ocr",
            "adres": adres,
            "meta": {
                "kaynak": "ocr",
                "path": adres,
                "source_address": adres,
                "chunk_index": i,
                "ocr": True,
                **_build_ocr_signal_meta(
                    kaynak_turu="image_ocr",
                    ocr_quality_meta=ocr_quality_meta,
                ),
                "format": "image",
                "document_family": "image",
                "office_document_type": "image",
                "office_unit_kind": "image",
                "office_unit_title": f"Gorsel {i}",
                "chunk_kind": "visual_ocr",
                "chunk_title": f"Gorsel OCR parcasi {i}",
                "baslik": f"Gorsel OCR parcasi {i}",
                "short_valid": base_quality_meta["short_valid"],
                "quality_score": combined_quality_score,
                "quality_reason": base_quality_meta["quality_reason"],
                "quality_advisory": bool(
                    base_quality_meta["quality_advisory"] or weak_content
                ),
                "ocr_quality_score": ocr_quality_meta["ocr_quality_score"],
                "ocr_quality_reason": ocr_quality_meta["ocr_quality_reason"],
                "ocr_alnum_density": ocr_quality_meta["ocr_alnum_density"],
                "ocr_garbage_ratio": ocr_quality_meta["ocr_garbage_ratio"],
                "ocr_short_meaningful": ocr_quality_meta["ocr_short_meaningful"],
                "ocr_confidence_band": ocr_quality_meta["ocr_confidence_band"],
                "ocr_warning": ocr_quality_meta["ocr_warning"],
                "weak_content": weak_content,
                "difficulty_score": difficulty_meta["difficulty_score"],
                "difficulty_reason": difficulty_meta["difficulty_reason"],
                "difficulty_advisory": difficulty_meta["difficulty_advisory"],
                "cheatsheet_priority_score": cheatsheet_meta["cheatsheet_priority_score"],
                "is_cheatsheet": cheatsheet_meta["is_cheatsheet"],
                "cheatsheet_reason": cheatsheet_meta["cheatsheet_reason"],
            },
            text_field: chunk,
        }
        if order_field:
            kwargs[order_field] = i
        bulk.append(Parca(**kwargs))

    if not bulk:
        return _save_ocr_failure(
            doc,
            kaynak_turu="ocr",
            mime=mime,
            hata_mesaji="OCR cikti kalitesi dusuk veya anlamsiz; guvenilir parca uretilemedi.",
            debug_ozeti={
                "ocr_strict_quality_mode": _ocr_strict_quality_mode_enabled(),
                "toplam_chunk_sayisi": len(chunks),
                "rejected_chunk_sayisi": rejected_chunks,
            },
        )

    aggregate = _ocr_chunk_aggregate(bulk, quality_rows)
    persistence = ingestion_bulkunu_kaydet(
        doc,
        bulk=bulk,
        kaynak_turu="ocr",
        mime=mime,
        kalite_durumu="ok",
        hata_mesaji="",
        debug_ozeti={
            "chunk_sayisi": len(chunks),
            "accepted_chunk_sayisi": aggregate["accepted_chunk_sayisi"],
            "rejected_chunk_sayisi": aggregate["rejected_chunk_sayisi"],
            "ocr_strict_quality_mode": _ocr_strict_quality_mode_enabled(),
            "ortalama_ocr_quality_score": aggregate["ocr_quality_score"],
            "ocr_confidence_band": aggregate["ocr_confidence_band"],
            "ocr_warning": aggregate["ocr_warning"],
            "ortalama_quality_score": aggregate["quality_score"],
            "ortalama_difficulty_score": aggregate["difficulty_score"],
        },
        batch_size=500,
        kayit_basarisiz_mesaji="OCR parcalari veritabanina kaydedilemedi.",
    )
    sonuc = persistence["sonuc"]
    real_count = persistence["real_count"]

    if sonuc["durum_gecisi"] != "parcalandi":
        return doc

    kaydet_skor_olayi(
        kullanici=doc.owner,
        olay_turu="ocr_ingestion_score_snapshot",
        kaynak_modul="ocr.ingestion",
        dokuman=doc,
        score_map={
            "quality_score": aggregate["quality_score"],
            "ocr_quality_score": aggregate["ocr_quality_score"],
            "difficulty_score": aggregate["difficulty_score"],
            "ocr_quality_reason": "aggregate_ocr_quality",
            "difficulty_reason": "aggregate_chunk_difficulty",
            "weak_content": aggregate["weak_content"],
            "ocr_strict_quality_mode": _ocr_strict_quality_mode_enabled(),
            "chunk_sayisi": aggregate["chunk_sayisi"],
            "accepted_chunk_sayisi": aggregate["accepted_chunk_sayisi"],
            "rejected_chunk_sayisi": aggregate["rejected_chunk_sayisi"],
            "kaydedilen_parca_sayisi": real_count,
        },
        durum="ok",
    )
    kaydet_skor_olayi(
        kullanici=doc.owner,
        olay_turu="multiformat_chunk_created",
        kaynak_modul="ocr.multiformat",
        dokuman=doc,
        score_map={
            "format": "image",
            "chunk_sayisi": aggregate["chunk_sayisi"],
            "kaydedilen_parca_sayisi": real_count,
            "quality_score": aggregate["quality_score"],
            "ocr_quality_score": aggregate["ocr_quality_score"],
            "difficulty_score": aggregate["difficulty_score"],
            "weak_content": aggregate["weak_content"],
        },
        durum="ok",
    )
    kaydet_skor_olayi(
        kullanici=doc.owner,
        olay_turu="multiformat_chunk_created",
        kaynak_modul="ocr.ingestion",
        dokuman=doc,
        score_map={
            "format": "image",
            "chunk_sayisi": aggregate["chunk_sayisi"],
            "kaydedilen_parca_sayisi": real_count,
            "quality_score": aggregate["quality_score"],
            "difficulty_score": aggregate["difficulty_score"],
            "chunk_kind": "visual_ocr",
        },
        durum="ok",
    )

    from dokuman.services.rag import sync_dokuman_indexi_if_enabled

    sync_dokuman_indexi_if_enabled(doc)
    return doc


def pdf_ocr_ile_parcala_ve_kaydet(
    doc,
    *,
    limit: int = 5000,
    fallback_reason: str = "",
    pdf_text_layer_summary: dict | None = None,
):
    if not getattr(settings, "OCR_ENABLED", True):
        return _save_ocr_failure(
            doc,
            kaynak_turu="ocr.pdf",
            mime="application/pdf",
            hata_mesaji="PDF OCR fallback kapalidir; OCR_ENABLED False.",
            debug_ozeti={"ocr_fallback_attempted": True},
        )

    file_path = getattr(getattr(doc, "dosya", None), "path", None)
    if not file_path:
        raise RuntimeError("Dokuman dosya yolu alinamadi.")

    ext = Path(file_path).suffix.lower()
    if ext != ".pdf":
        raise RuntimeError(f"Desteklenmeyen PDF OCR fallback uzantisi: {ext}")

    page_rows = extract_text_from_pdf_pages(file_path)
    if not page_rows:
        return _save_ocr_failure(
            doc,
            kaynak_turu="ocr.pdf",
            mime="application/pdf",
            hata_mesaji="PDF OCR fallback hic metin cikaramadi. Mumkunse belgeyi daha net tarayip tekrar yukleyin.",
            debug_ozeti={
                "ocr_fallback_attempted": True,
                "ocr_fallback_reason": str(fallback_reason or ""),
                "page_count": 0,
            },
        )

    chunk_size = int(getattr(settings, "OCR_PDF_CHUNK_SIZE", getattr(settings, "OCR_CHUNK_SIZE", 1200)) or 1200)
    text_field = _parca_text_field_name()
    order_field = _parca_order_field_name()

    bulk = []
    quality_rows = []
    page_count = len(page_rows)
    successful_pages = 0
    rejected_chunks = 0
    summary = dict(pdf_text_layer_summary or {})

    for page_row in page_rows:
        page_no = int(page_row.get("page") or 0)
        page_text = normalize_ocr_text(str(page_row.get("text") or ""))
        if not page_text:
            continue

        page_chunks = split_text_into_chunks(page_text, max_chars=chunk_size) or [page_text]
        page_chunk_added = False
        for page_chunk_index, chunk in enumerate(page_chunks, start=1):
            chunk = (chunk or "").strip()
            if not chunk:
                continue
            if len(bulk) >= int(limit or 0):
                break

            adres = f"pdf:page:{page_no}#ocr:{page_chunk_index}"
            base_quality_meta = _quality_score_analizi(
                chunk,
                icerik_uzunlugu=len(chunk),
                ocr=True,
            )
            ocr_quality_meta = analyze_ocr_quality(chunk)
            difficulty_meta = _difficulty_score_analizi(chunk, ocr=True)
            cheatsheet_meta = analyze_cheatsheet_priority(chunk)
            combined_quality_score = round(
                min(
                    1.0,
                    (0.7 * float(base_quality_meta["quality_score"]))
                    + (0.3 * float(ocr_quality_meta["ocr_quality_score"])),
                ),
                3,
            )
            weak_content = bool(
                base_quality_meta["weak_content"] or ocr_quality_meta["weak_content"]
            )
            quality_rows.append(
                {
                    "quality_score": combined_quality_score,
                    "ocr_quality_score": ocr_quality_meta["ocr_quality_score"],
                    "difficulty_score": difficulty_meta["difficulty_score"],
                    "weak_content": weak_content,
                    "ocr_confidence_band": ocr_quality_meta["ocr_confidence_band"],
                    "ocr_warning": ocr_quality_meta["ocr_warning"],
                    "accepted": False,
                }
            )
            accepted = _ocr_chunk_is_acceptable(
                chunk=chunk,
                base_quality_meta=base_quality_meta,
                ocr_quality_meta=ocr_quality_meta,
                combined_quality_score=combined_quality_score,
            )
            if _ocr_strict_quality_mode_enabled() and combined_quality_score < 0.62:
                accepted = False
            quality_rows[-1]["accepted"] = accepted
            if not accepted:
                rejected_chunks += 1
                continue

            page_chunk_added = True
            kwargs = {
                "dokuman": doc,
                "tur": "ocr",
                "adres": adres,
                "meta": {
                    "kaynak": "ocr.pdf",
                    "path": adres,
                    "source_address": adres,
                    "chunk_index": len(bulk) + 1,
                    "page_chunk_index": page_chunk_index,
                    "page": page_no,
                    "sayfa": page_no,
                    "page_address": f"pdf:page:{page_no}",
                    "ocr": True,
                    "ocr_fallback": True,
                    "ocr_source": "pdf_page_render",
                    **_build_ocr_signal_meta(
                        kaynak_turu="pdf_ocr_fallback",
                        ocr_quality_meta=ocr_quality_meta,
                    ),
                    "format": "pdf",
                    "document_family": "pdf",
                    "office_document_type": "pdf",
                    "office_unit_kind": "page",
                    "office_unit_title": f"Sayfa {page_no}",
                    "chunk_kind": "visual_ocr",
                    "chunk_title": f"PDF sayfa {page_no} OCR",
                    "baslik": f"PDF sayfa {page_no} OCR",
                    "short_valid": base_quality_meta["short_valid"],
                    "quality_score": combined_quality_score,
                    "quality_reason": base_quality_meta["quality_reason"],
                    "quality_advisory": bool(
                        base_quality_meta["quality_advisory"] or weak_content
                    ),
                    "ocr_quality_score": ocr_quality_meta["ocr_quality_score"],
                    "ocr_quality_reason": ocr_quality_meta["ocr_quality_reason"],
                    "ocr_alnum_density": ocr_quality_meta["ocr_alnum_density"],
                    "ocr_garbage_ratio": ocr_quality_meta["ocr_garbage_ratio"],
                    "ocr_short_meaningful": ocr_quality_meta["ocr_short_meaningful"],
                    "ocr_confidence_band": ocr_quality_meta["ocr_confidence_band"],
                    "ocr_warning": ocr_quality_meta["ocr_warning"],
                    "weak_content": weak_content,
                    "difficulty_score": difficulty_meta["difficulty_score"],
                    "difficulty_reason": difficulty_meta["difficulty_reason"],
                    "difficulty_advisory": difficulty_meta["difficulty_advisory"],
                    "cheatsheet_priority_score": cheatsheet_meta["cheatsheet_priority_score"],
                    "is_cheatsheet": cheatsheet_meta["is_cheatsheet"],
                    "cheatsheet_reason": cheatsheet_meta["cheatsheet_reason"],
                    "image_width": int(page_row.get("image_width") or 0),
                    "image_height": int(page_row.get("image_height") or 0),
                },
                text_field: chunk,
            }
            if order_field:
                kwargs[order_field] = len(bulk) + 1
            bulk.append(Parca(**kwargs))

        if page_chunk_added:
            successful_pages += 1
        if len(bulk) >= int(limit or 0):
            break

    if not bulk:
        return _save_ocr_failure(
            doc,
            kaynak_turu="ocr.pdf",
            mime="application/pdf",
            hata_mesaji="PDF OCR fallback cikti kalitesi dusuk veya anlamsiz; guvenilir parca uretemedi. Mumkunse belgeyi daha net tarayip tekrar yukleyin.",
            debug_ozeti={
                "ocr_fallback_attempted": True,
                "ocr_fallback_reason": str(fallback_reason or ""),
                "page_count": page_count,
                "successful_pages": successful_pages,
                "rejected_chunk_sayisi": rejected_chunks,
                "ocr_strict_quality_mode": _ocr_strict_quality_mode_enabled(),
                "text_layer_detected": bool(summary.get("text_layer_detected")),
                "text_layer_contentful_pages": int(summary.get("contentful_pages") or 0),
            },
        )

    aggregate = _ocr_chunk_aggregate(bulk, quality_rows)
    persistence = ingestion_bulkunu_kaydet(
        doc,
        bulk=bulk,
        kaynak_turu="ocr.pdf",
        mime="application/pdf",
        kalite_durumu="ok",
        hata_mesaji="",
        debug_ozeti={
            "ocr_fallback_attempted": True,
            "ocr_fallback_reason": str(fallback_reason or ""),
            "ocr_fallback_used": True,
            "page_count": page_count,
            "successful_pages": successful_pages,
            "chunk_sayisi": aggregate["chunk_sayisi"],
            "accepted_chunk_sayisi": aggregate["accepted_chunk_sayisi"],
            "rejected_chunk_sayisi": aggregate["rejected_chunk_sayisi"],
            "ocr_strict_quality_mode": _ocr_strict_quality_mode_enabled(),
            "ortalama_ocr_quality_score": aggregate["ocr_quality_score"],
            "ocr_confidence_band": aggregate["ocr_confidence_band"],
            "ocr_warning": aggregate["ocr_warning"],
            "ortalama_quality_score": aggregate["quality_score"],
            "ortalama_difficulty_score": aggregate["difficulty_score"],
            "text_layer_detected": bool(summary.get("text_layer_detected")),
            "text_layer_contentful_pages": int(summary.get("contentful_pages") or 0),
            "text_layer_total_chars": int(summary.get("total_chars") or 0),
        },
        batch_size=500,
        kayit_basarisiz_mesaji="PDF OCR parcalari veritabanina kaydedilemedi.",
    )
    sonuc = persistence["sonuc"]
    real_count = persistence["real_count"]

    if sonuc["durum_gecisi"] != "parcalandi":
        return doc

    if getattr(doc, "owner_id", None):
        kaydet_skor_olayi(
            kullanici=doc.owner,
            olay_turu="ocr_ingestion_score_snapshot",
            kaynak_modul="ocr.pdf_ingestion",
            dokuman=doc,
            score_map={
                "quality_score": aggregate["quality_score"],
                "ocr_quality_score": aggregate["ocr_quality_score"],
                "difficulty_score": aggregate["difficulty_score"],
                "ocr_quality_reason": "aggregate_ocr_quality",
                "difficulty_reason": "aggregate_chunk_difficulty",
                "weak_content": aggregate["weak_content"],
                "ocr_strict_quality_mode": _ocr_strict_quality_mode_enabled(),
                "chunk_sayisi": aggregate["chunk_sayisi"],
                "accepted_chunk_sayisi": aggregate["accepted_chunk_sayisi"],
                "rejected_chunk_sayisi": aggregate["rejected_chunk_sayisi"],
                "kaydedilen_parca_sayisi": real_count,
                "page_count": page_count,
                "successful_pages": successful_pages,
            },
            durum="ok",
        )
        kaydet_skor_olayi(
            kullanici=doc.owner,
            olay_turu="multiformat_chunk_created",
            kaynak_modul="ocr.pdf",
            dokuman=doc,
            score_map={
                "format": "pdf",
                "chunk_sayisi": aggregate["chunk_sayisi"],
                "kaydedilen_parca_sayisi": real_count,
                "quality_score": aggregate["quality_score"],
                "ocr_quality_score": aggregate["ocr_quality_score"],
                "difficulty_score": aggregate["difficulty_score"],
                "weak_content": aggregate["weak_content"],
                "chunk_kind": "visual_ocr",
                "ocr_fallback": True,
                "page_count": page_count,
                "successful_pages": successful_pages,
            },
            durum="ok",
        )

    from dokuman.services.rag import sync_dokuman_indexi_if_enabled

    sync_dokuman_indexi_if_enabled(doc)
    return doc
