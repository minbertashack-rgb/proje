from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
import re

from django.conf import settings


# ---------------------------------------------------
# DATA MODELS
# ---------------------------------------------------

@dataclass
class TextBlock:
    text: str
    page: int = 1
    font_size: float = 12.0
    bold: bool = False
    style_name: str = ""
    x0: float = 0.0
    y0: float = 0.0
    explicit_heading: bool = False
    explicit_level: int | None = None


@dataclass
class SectionNode:
    title: str
    level: int
    page_start: int
    content_lines: list[str] = field(default_factory=list)
    children: list["SectionNode"] = field(default_factory=list)
    path: str = ""
    debug_meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = {
            "title": self.title,
            "level": self.level,
            "page_start": self.page_start,
            "path": self.path,
            "content": "\n".join(x for x in self.content_lines if x).strip(),
            "children": [c.to_dict() for c in self.children],
        }
        if self.debug_meta:
            out.update(self.debug_meta)
        return out


# ---------------------------------------------------
# TEXT HELPERS
# ---------------------------------------------------

_SENTENCE_END_RE = re.compile(r"[.!?]\s*$")
_NUM_HEADING_RE = re.compile(
    r"^\s*(\d+(?:\.\d+){0,5})[\)\.-]?\s+\S+"
)
_ROMAN_HEADING_RE = re.compile(
    r"^\s*([IVXLCM]+)[\)\.-]?\s+\S+",
    re.IGNORECASE,
)
_LETTER_HEADING_RE = re.compile(
    r"^\s*([A-ZÇĞİÖŞÜ])[\)\.-]\s+\S+"
)
_VERB_HINT_RE = re.compile(
    r"(maktadir|mektedir|yor|yorlar|mistir|miştir|dir|tir|dur|tur|ir|ar|er|ur|tanimlar|aciklar|anlatir|gosterir|icerir|sunar|vurgular)$",
    re.IGNORECASE,
)
_SPECIAL_HEADING_RE = re.compile(
    r"^\s*(BÖLÜM|BOLUM|CHAPTER|SECTION|EK|APPENDIX|GİRİŞ|GIRIS|SONUÇ|SONUC|ÖZET|OZET)\b",
    re.IGNORECASE,
)
_SHORT_VALID_HEADINGS = {
    "amac", "amaç", "tanim", "tanım", "ozet", "özet", "sonuc", "sonuç",
    "yontem", "yöntem", "kapsam", "giris", "giriş", "bulgu", "bulgular",
    "degerlendirme", "değerlendirme",
}


def _heading_score_enabled() -> bool:
    return bool(getattr(settings, "DOCVERSE_HEADING_SCORE_ENABLED", True))


def _debug_summary_enabled() -> bool:
    return bool(getattr(settings, "DOCVERSE_DEBUG_SUMMARY_ENABLED", False))


def _is_strict_special_heading(text: str) -> bool:
    text = normalize_text(text)
    if not text:
        return False

    m = _SPECIAL_HEADING_RE.match(text)
    if not m:
        return False

    if ends_like_sentence(text):
        return False

    remainder = text[m.end():].strip()

    # Standalone keyword
    if not remainder:
        return True

    # Keyword punctuation variants
    if remainder.startswith(":") or remainder.startswith("-"):
        return True

    # Çok uzun değilse, kısa başlıksal devam metinden vazgeçme
    if word_count(text) <= 6:
        return True

    return False


def normalize_text(text: str) -> str:
    text = (text or "").replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def word_count(text: str) -> int:
    return len(normalize_text(text).split())


def is_all_caps_like(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return (upper / len(letters)) >= 0.80


def ends_like_sentence(text: str) -> bool:
    return bool(_SENTENCE_END_RE.search(text.strip()))


def punctuation_density(text: str) -> int:
    return len(re.findall(r"[,;:]", text or ""))


def numbered_depth(text: str) -> int | None:
    text = normalize_text(text)
    wc = word_count(text)

    if not text:
        return None

    if len(text) > 140:
        return None

    m = _NUM_HEADING_RE.match(text)
    if m:
        if wc > 14 and ends_like_sentence(text):
            return None
        return m.group(1).count(".") + 1

    if _ROMAN_HEADING_RE.match(text) and wc <= 10 and not ends_like_sentence(text):
        return 1

    if _LETTER_HEADING_RE.match(text) and wc <= 10 and not ends_like_sentence(text):
        return 2

    if _is_strict_special_heading(text):
        return 1

    return None


def style_heading_level(style_name: str) -> int | None:
    style_name = (style_name or "").strip()
    if not style_name:
        return None

    m = re.search(r"(heading|başlık|baslik)\s*(\d+)", style_name, re.IGNORECASE)
    if m:
        return max(1, min(int(m.group(2)), 6))

    if re.fullmatch(r"(title|başlık|baslik)", style_name, re.IGNORECASE):
        return 1

    return None


def resolved_heading_level(block: TextBlock) -> int | None:
    if block.explicit_level:
        return max(1, min(block.explicit_level, 6))

    style_level = style_heading_level(block.style_name)
    if style_level is not None:
        return style_level

    depth = numbered_depth(block.text)
    if depth is not None:
        return max(1, min(depth, 6))

    return None


def looks_like_sparse_heading(text: str) -> bool:
    text = normalize_text(text)
    wc = word_count(text)

    if not text:
        return False

    if numbered_depth(text) is not None or _SPECIAL_HEADING_RE.match(text):
        return False

    if wc <= 2 and len(text) <= 24:
        return True

    if wc <= 4 and len(text) <= 28 and punctuation_density(text) == 0 and not ends_like_sentence(text):
        return True

    return False


def looks_like_clean_short_heading(text: str) -> bool:
    text = normalize_text(text)
    wc = word_count(text)

    if not text:
        return False

    if wc > 4 or len(text) > 36:
        return False

    if ends_like_sentence(text):
        return False

    if punctuation_density(text) > 1:
        return False

    if text[:1].islower():
        return False

    return True


def looks_like_semantic_short_heading(text: str) -> bool:
    text = normalize_text(text)
    if not text:
        return False
    if word_count(text) > 3 or len(text) > 32:
        return False
    if ends_like_sentence(text):
        return False

    toks = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", text.lower())
    if not toks:
        return False
    return all(tok in _SHORT_VALID_HEADINGS for tok in toks)


def looks_like_dense_paragraph(text: str) -> bool:
    text = normalize_text(text)
    wc = word_count(text)

    if len(text) >= 100 and wc >= 10:
        return True

    if wc >= 15:
        return True

    if wc >= 18:
        return True

    if wc >= 12 and ends_like_sentence(text):
        return True

    if wc >= 10 and punctuation_density(text) >= 2:
        return True

    return False


def looks_like_subsection_title(text: str) -> bool:
    lowered = normalize_text(text).lower()
    return lowered.startswith(("alt ", "alt-", "sub ", "sub-", "ara ", "ara-"))


def looks_like_uppercase_explanatory_line(text: str, block: TextBlock, body_font: float) -> bool:
    text = normalize_text(text)
    wc = word_count(text)

    if not text or not is_all_caps_like(text):
        return False

    if block.explicit_heading or style_heading_level(block.style_name) is not None:
        return False

    if numbered_depth(text) is not None or _is_strict_special_heading(text):
        return False

    if wc < 6 or len(text) < 32:
        return False

    if block.font_size >= body_font + 2.8:
        return False

    if ends_like_sentence(text):
        return True

    if punctuation_density(text) >= 1:
        return True

    return wc >= 7


def looks_like_overlong_heading_candidate(text: str, block: TextBlock) -> bool:
    text = normalize_text(text)
    wc = word_count(text)

    if not text:
        return False

    if block.explicit_heading or style_heading_level(block.style_name) is not None:
        return False

    if numbered_depth(text) is not None or _is_strict_special_heading(text):
        return False

    if wc >= 14:
        return True

    if len(text) >= 90 and wc >= 9:
        return True

    return False


def looks_like_plain_sentence_paragraph(text: str, block: TextBlock, body_font: float) -> bool:
    text = normalize_text(text)
    wc = word_count(text)
    style_level = style_heading_level(block.style_name)
    numeric_level = numbered_depth(text)

    if not text:
        return False

    if block.explicit_heading or style_level is not None or numeric_level is not None:
        return False

    if not ends_like_sentence(text):
        return False

    if wc < 2 or wc > 14:
        return False

    if block.bold:
        return False

    if block.font_size >= body_font + 1.8:
        return False

    if is_all_caps_like(text):
        return False

    return True


def looks_like_short_explanatory_line(text: str, block: TextBlock, body_font: float) -> bool:
    text = normalize_text(text)
    wc = word_count(text)
    tokens = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", text.lower())

    if not text:
        return False

    if block.explicit_heading or style_heading_level(block.style_name) is not None:
        return False

    if numbered_depth(text) is not None or _is_strict_special_heading(text):
        return False

    if ends_like_sentence(text):
        return False

    if wc < 5 or wc > 12:
        return False

    if block.font_size >= body_font + 2.4:
        return False

    if is_all_caps_like(text):
        return False

    if not tokens:
        return False

    if tokens[0] in {"bu", "su", "burada", "metin", "parca", "dokuman", "belge"}:
        return True

    return any(_VERB_HINT_RE.search(tok) for tok in tokens[-3:])


def looks_like_tableish_noise(text: str) -> bool:
    text = normalize_text(text)
    if not text:
        return False

    if numbered_depth(text) is not None or _is_strict_special_heading(text):
        return False

    if "|" in text and word_count(text) <= 8:
        return True

    if text.count("/") >= 2 and word_count(text) <= 6 and not ends_like_sentence(text):
        return True

    if punctuation_density(text) >= 3 and word_count(text) <= 7 and not ends_like_sentence(text):
        return True

    return False


def looks_like_broken_ocr_line(text: str) -> bool:
    text = normalize_text(text)
    if not text:
        return False

    tokens = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]+", text)
    if len(tokens) < 6:
        return False

    single_char_tokens = sum(1 for tok in tokens if len(tok) == 1)
    if (single_char_tokens / len(tokens)) < 0.55:
        return False

    long_tokens = [tok for tok in tokens if len(tok) >= 3]
    if long_tokens:
        return False

    # Tek harfe bolunmus OCR satirlari bazen tumu buyuk harf olarak gelir, bazen de
    # rakam/harf karisik davranir. Her iki durumda da yapisal baslik gibi ele almak riskli.
    alpha_numeric_mix = sum(1 for tok in tokens if any(ch.isalpha() for ch in tok) or any(ch.isdigit() for ch in tok))
    return alpha_numeric_mix >= 6


def normalize_section_path(path: str, *, fallback: str = "0") -> str:
    clean = normalize_text(path).replace(" ", "")
    clean = re.sub(r"[^0-9.]+", "", clean)
    clean = re.sub(r"\.+", ".", clean).strip(".")
    return clean or str(fallback or "0")


def build_child_section_path(parent_path: str, next_idx: int) -> str:
    parent = normalize_section_path(parent_path, fallback="0")
    if parent == "0":
        return normalize_section_path(str(next_idx), fallback=str(next_idx))
    return normalize_section_path(f"{parent}.{int(next_idx)}", fallback=str(next_idx))


def _same_visual_family(a: TextBlock, b: TextBlock) -> bool:
    if a.style_name and b.style_name and a.style_name.lower() == b.style_name.lower():
        return True

    same_font_band = abs(float(a.font_size or 0.0) - float(b.font_size or 0.0)) <= 0.6
    same_bold = bool(a.bold) == bool(b.bold)
    return same_font_band and same_bold


def _likely_heading_candidate(block: TextBlock, body_font: float) -> bool:
    text = normalize_text(block.text)
    if not text:
        return False

    if block.explicit_heading or style_heading_level(block.style_name) is not None:
        return True

    if numbered_depth(text) is not None:
        return True

    if looks_like_uppercase_explanatory_line(text, block, body_font):
        return False

    if looks_like_broken_ocr_line(text):
        return False

    if looks_like_short_explanatory_line(text, block, body_font):
        return False

    if looks_like_overlong_heading_candidate(text, block):
        return False

    if looks_like_dense_paragraph(text):
        return False

    return (
        word_count(text) <= 10
        and not ends_like_sentence(text)
        and (
            block.bold
            or block.font_size >= body_font + 1.0
            or is_all_caps_like(text)
        )
    )


def _should_merge_heading_with_next(blocks: list[TextBlock], idx: int, body_font: float) -> bool:
    if idx + 1 >= len(blocks):
        return False

    current = blocks[idx]
    nxt = blocks[idx + 1]
    current_text = normalize_text(current.text)
    next_text = normalize_text(nxt.text)

    if not current_text or not next_text:
        return False

    if current.page != nxt.page:
        return False

    if not _likely_heading_candidate(current, body_font):
        return False

    if nxt.explicit_heading or style_heading_level(nxt.style_name) is not None:
        return False

    if str(nxt.style_name or "").strip().lower() == "table":
        return False

    if numbered_depth(next_text) is not None:
        return False

    if looks_like_dense_paragraph(next_text):
        return False

    if word_count(next_text) > 8 or len(next_text) > 80:
        return False

    if ends_like_sentence(next_text):
        return False

    if punctuation_density(next_text) >= 2:
        return False

    if not _same_visual_family(current, nxt):
        return False

    return True


def merge_multiline_heading_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    clean_blocks = [b for b in blocks if normalize_text(b.text)]
    if not clean_blocks:
        return []

    font_values = [b.font_size for b in clean_blocks if b.font_size > 0]
    body_font = median(font_values) if font_values else 12.0

    merged: list[TextBlock] = []
    i = 0

    while i < len(clean_blocks):
        current = clean_blocks[i]
        merged_text = normalize_text(current.text)
        j = i

        while _should_merge_heading_with_next(clean_blocks, j, body_font):
            nxt = clean_blocks[j + 1]
            merged_text = normalize_text(f"{merged_text} {normalize_text(nxt.text)}")
            j += 1

        if j > i:
            final_block = TextBlock(
                text=merged_text,
                page=current.page,
                font_size=max(b.font_size for b in clean_blocks[i:j + 1]),
                bold=any(b.bold for b in clean_blocks[i:j + 1]),
                style_name=current.style_name,
                x0=current.x0,
                y0=current.y0,
                explicit_heading=current.explicit_heading,
                explicit_level=current.explicit_level,
            )
            merged.append(final_block)
            i = j + 1
            continue

        merged.append(current)
        i += 1

    return merged


# ---------------------------------------------------
# HEADING DETECTION
# ---------------------------------------------------

def heading_score_details(block: TextBlock, body_font: float) -> dict:
    text = normalize_text(block.text)
    wc = word_count(text)
    style_level = style_heading_level(block.style_name)
    numeric_level = numbered_depth(text)
    special_heading = _is_strict_special_heading(text)

    if not text:
        return {
            "heading_score": 0.0,
            "heading_decision_reason": "empty_text",
            "heading_positive_signals": [],
            "heading_penalty_signals": ["empty_text"],
        }

    score = 0.0
    positive_signals: list[str] = []
    penalty_signals: list[str] = []
    size_ratio = max(0.0, float(block.font_size or 0.0) / max(float(body_font or 12.0), 1.0))
    size_signal = min(size_ratio, 1.5)
    bold_signal = 1.0 if block.bold else 0.0
    numbering_signal = 1.0 if (numeric_level is not None or special_heading) else 0.0
    length_penalty = max(0.0, (len(text) - 80) / 100.0)

    score += 0.4 * size_signal
    score += 0.3 * bold_signal
    score += 0.4 * numbering_signal

    if size_signal > 1.0:
        positive_signals.append("larger_font")
    if block.bold:
        positive_signals.append("bold_heading")
    if numbering_signal > 0:
        positive_signals.append("numbered_heading")

    if block.explicit_heading:
        score += 0.25
        positive_signals.append("explicit_heading")

    if style_level is not None:
        score += 0.20
        positive_signals.append("style_heading")

    if looks_like_clean_short_heading(text):
        score += 0.08
        positive_signals.append("clean_short_heading")

    if looks_like_clean_short_heading(text) and word_count(text) <= 3 and block.font_size >= body_font + 0.4:
        score += 0.05
        positive_signals.append("short_heading_font_lift")

    if looks_like_semantic_short_heading(text):
        score += 0.12
        positive_signals.append("short_valid_heading")

    if looks_like_subsection_title(text) and block.font_size >= body_font + 1.0:
        score += 0.18
        positive_signals.append("subsection_heading")

    if special_heading:
        score += 0.05
        positive_signals.append("special_heading_keyword")

    score -= length_penalty
    if length_penalty > 0:
        penalty_signals.append("long_line_penalty")

    if ends_like_sentence(text):
        score -= 0.30
        penalty_signals.append("sentence_ending_penalty")

    if looks_like_plain_sentence_paragraph(text, block, body_font):
        score -= 0.35
        penalty_signals.append("plain_sentence_penalty")

    if looks_like_short_explanatory_line(text, block, body_font):
        score -= 0.30
        penalty_signals.append("short_explanatory_penalty")

    if looks_like_tableish_noise(text):
        score -= 0.38
        penalty_signals.append("tableish_noise_penalty")

    if looks_like_broken_ocr_line(text):
        score -= 0.42
        penalty_signals.append("broken_ocr_penalty")

    if looks_like_dense_paragraph(text):
        score -= 0.25
        penalty_signals.append("dense_paragraph_penalty")

    if looks_like_uppercase_explanatory_line(text, block, body_font):
        score -= 0.35
        penalty_signals.append("all_caps_false_positive_penalty")

    if looks_like_overlong_heading_candidate(text, block):
        score -= 0.22
        penalty_signals.append("overlong_heading_penalty")

    if punctuation_density(text) >= 2:
        score -= 0.12
        penalty_signals.append("heavy_punctuation_penalty")

    if wc > 20:
        score -= 0.18
        penalty_signals.append("long_word_count_penalty")

    if text[:1].islower():
        score -= 0.10
        penalty_signals.append("lowercase_start_penalty")

    if looks_like_sparse_heading(text) and not (
        block.explicit_heading
        or style_level is not None
        or numeric_level is not None
        or block.bold
        or block.font_size >= body_font + 0.4
    ):
        score -= 0.18
        penalty_signals.append("sparse_heading_penalty")

    if _heading_score_enabled() and wc <= 8 and ends_like_sentence(text) and numeric_level is None and style_level is None:
        score -= 0.10
        penalty_signals.append("short_sentence_false_positive_penalty")

    if _heading_score_enabled() and is_all_caps_like(text) and wc >= 5 and not special_heading and numeric_level is None:
        score -= 0.08
        penalty_signals.append("all_caps_warning_penalty")

    if penalty_signals:
        reason = penalty_signals[0]
    elif positive_signals:
        reason = positive_signals[0]
    else:
        reason = "neutral_heading_score"

    return {
        "heading_score": round(clamp01(score), 3),
        "heading_decision_reason": reason,
        "heading_positive_signals": positive_signals[:4],
        "heading_penalty_signals": penalty_signals[:4],
    }


def heading_score(block: TextBlock, body_font: float) -> float:
    return float(heading_score_details(block, body_font)["heading_score"])


def is_heading(block: TextBlock, body_font: float, threshold: float = 0.65) -> bool:
    if block.explicit_heading:
        return True

    text = normalize_text(block.text)

    if looks_like_uppercase_explanatory_line(text, block, body_font):
        return False

    if looks_like_tableish_noise(text):
        return False

    if looks_like_broken_ocr_line(text):
        return False

    if looks_like_overlong_heading_candidate(text, block):
        return False

    if looks_like_plain_sentence_paragraph(text, block, body_font):
        return False

    if looks_like_short_explanatory_line(text, block, body_font):
        return False

    return heading_score(block, body_font) >= threshold


def infer_level(block: TextBlock, heading_sizes_desc: list[float], body_font: float) -> int:
    text = normalize_text(block.text)

    level = resolved_heading_level(block)
    if level is not None:
        return level

    if _is_strict_special_heading(text):
        return 1

    if heading_sizes_desc:
        closest = min(heading_sizes_desc, key=lambda s: abs(s - block.font_size))
        rank = heading_sizes_desc.index(closest) + 1
        if rank == 2 and len(heading_sizes_desc) == 2 and not looks_like_subsection_title(text):
            return 1
        return max(1, min(rank, 6))

    # fallback
    if block.font_size >= body_font + 4:
        return 1
    if block.font_size >= body_font + 2:
        return 2
    if block.font_size >= body_font + 1:
        return 3
    return 4


# ---------------------------------------------------
# TREE BUILDING
# ---------------------------------------------------

def build_section_tree(blocks: list[TextBlock]) -> SectionNode:
    clean_blocks = merge_multiline_heading_blocks(blocks)
    if not clean_blocks:
        return SectionNode(title="ROOT", level=0, page_start=1)

    font_values = [b.font_size for b in clean_blocks if b.font_size > 0]
    body_font = median(font_values) if font_values else 12.0

    heading_blocks = [b for b in clean_blocks if is_heading(b, body_font)]
    heading_sizes_desc = sorted(
        {round(b.font_size, 1) for b in heading_blocks if b.font_size > 0},
        reverse=True
    )

    root = SectionNode(title="ROOT", level=0, page_start=1, path="")
    intro = SectionNode(title="Belge Başlangıcı", level=1, page_start=1, path="0")
    has_started = False
    stack: list[SectionNode] = [root]

    heading_index_stack: list[int] = []

    for block in clean_blocks:
        text = normalize_text(block.text)

        if is_heading(block, body_font):
            has_started = True
            level = infer_level(block, heading_sizes_desc, body_font)
            debug_meta = heading_score_details(block, body_font) if _debug_summary_enabled() else {}

            while len(stack) > 1 and stack[-1].level >= level:
                stack.pop()
                if heading_index_stack:
                    heading_index_stack.pop()

            parent = stack[-1]
            next_idx = len(parent.children) + 1
            current_path = build_child_section_path(parent.path, next_idx)

            node = SectionNode(
                title=text,
                level=level,
                page_start=block.page,
                path=current_path,
                debug_meta=debug_meta,
            )
            parent.children.append(node)
            stack.append(node)
            heading_index_stack.append(next_idx)

        else:
            if not has_started:
                intro.content_lines.append(text)
            else:
                stack[-1].content_lines.append(text)

    if intro.content_lines:
        root.children.insert(0, intro)

    return root


def flatten_sections(root: SectionNode) -> list[dict]:
    result = []

    def should_emit(node: SectionNode) -> bool:
        content = normalize_text("\n".join(x for x in node.content_lines if x))
        title = normalize_text(node.title)

        if content:
            return True

        if not title:
            return False

        if node.children and looks_like_sparse_heading(title):
            return False

        if looks_like_sparse_heading(title) and len(title) < 20:
            return False

        return True

    def walk(node: SectionNode):
        if node.level > 0 and should_emit(node):
            item = node.to_dict()
            item["path"] = normalize_section_path(item.get("path") or "", fallback="0")
            result.append(item)
        for child in node.children:
            walk(child)

    for child in root.children:
        walk(child)

    return result


# ---------------------------------------------------
# DOCX PARSER
# ---------------------------------------------------

def parse_docx_blocks(file_path: str | Path) -> list[TextBlock]:
    from docx import Document  # python-docx
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(file_path))
    blocks: list[TextBlock] = []

    page_no = 1  # docx için gerçek sayfa zor, şimdilik 1 kabul ediyoruz

    def _iter_docx_items():
        body = doc.element.body
        for child in body.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, doc)
            elif isinstance(child, CT_Tbl):
                yield Table(child, doc)

    table_no = 0
    for item in _iter_docx_items():
        if isinstance(item, Paragraph):
            p = item
            text = normalize_text(p.text)
            if not text:
                continue

            style_name = ""
            explicit_heading = False
            explicit_level = None

            try:
                style_name = (p.style.name or "").strip()
            except Exception:
                style_name = ""

            style_level = style_heading_level(style_name)
            if style_level is not None:
                explicit_heading = True
                explicit_level = style_level

            run_sizes = []
            is_bold = False

            for r in p.runs:
                try:
                    if r.bold:
                        is_bold = True
                except Exception:
                    pass

                try:
                    if r.font and r.font.size:
                        run_sizes.append(float(r.font.size.pt))
                except Exception:
                    pass

            font_size = max(run_sizes) if run_sizes else 12.0

            blocks.append(
                TextBlock(
                    text=text,
                    page=page_no,
                    font_size=font_size,
                    bold=is_bold,
                    style_name=style_name,
                    explicit_heading=explicit_heading,
                    explicit_level=explicit_level,
                )
            )
            continue

        table_no += 1
        for row_index, row in enumerate(item.rows, start=1):
            cells = [normalize_text(cell.text) for cell in row.cells if normalize_text(cell.text)]
            if not cells:
                continue
            row_text = normalize_text(f"Tablo {table_no} Satir {row_index}: {' | '.join(cells[:8])}")
            if not row_text:
                continue
            blocks.append(
                TextBlock(
                    text=row_text,
                    page=page_no,
                    font_size=11.5,
                    bold=False,
                    style_name="Table",
                )
            )

    return blocks


# ---------------------------------------------------
# PDF PARSER
# ---------------------------------------------------

def parse_pdf_blocks(file_path: str | Path) -> list[TextBlock]:
    import fitz  # PyMuPDF

    doc = fitz.open(str(file_path))
    blocks: list[TextBlock] = []

    for page_index, page in enumerate(doc, start=1):
        data = page.get_text("dict")
        for block in data.get("blocks", []):
            if "lines" not in block:
                continue

            for line in block["lines"]:
                spans = line.get("spans", [])
                if not spans:
                    continue

                text = normalize_text("".join(span.get("text", "") for span in spans))
                if not text:
                    continue

                sizes = [float(span.get("size", 12.0)) for span in spans if span.get("text", "").strip()]
                fonts = [str(span.get("font", "")) for span in spans]
                bbox = line.get("bbox", [0, 0, 0, 0])

                font_size = max(sizes) if sizes else 12.0
                is_bold = any("bold" in f.lower() for f in fonts)

                blocks.append(
                    TextBlock(
                        text=text,
                        page=page_index,
                        font_size=font_size,
                        bold=is_bold,
                        x0=float(bbox[0]) if bbox else 0.0,
                        y0=float(bbox[1]) if bbox else 0.0,
                    )
                )

    return blocks


# ---------------------------------------------------
# PUBLIC API
# ---------------------------------------------------

def parse_document_structure(file_path: str | Path) -> dict:
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".docx":
        blocks = parse_docx_blocks(path)
    elif ext == ".pdf":
        blocks = parse_pdf_blocks(path)
    else:
        raise ValueError(f"Desteklenmeyen dosya türü: {ext}")

    root = build_section_tree(blocks)
    sections = flatten_sections(root)
    out = {
        "file": str(path),
        "section_count": len(sections),
        "tree": root.to_dict(),
        "sections": sections,
    }
    if _debug_summary_enabled():
        heading_reason_ozeti = {}
        for sec in sections:
            reason = str(sec.get("heading_decision_reason") or "").strip()
            if reason:
                heading_reason_ozeti[reason] = heading_reason_ozeti.get(reason, 0) + 1
        out["debug_ozeti"] = {
            "heading_score_aktif_mi": _heading_score_enabled(),
            "heading_reason_ozeti": heading_reason_ozeti,
        }
    return out
