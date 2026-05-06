from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
from django.utils import timezone


class ExportError(Exception):
    pass


@dataclass
class RenderResult:
    content: bytes
    content_type: str
    filename: str


def build_cheatsheet_markdown(dokuman) -> str:
    """
    Sende Dokuman: baslik, durum, hata, created_at var.
    Sende Parca: metin, adres, zorluk_skoru, zorluk var.
    Basit bir cheatsheet üretelim: başlık + ilk 50 parça başlığı/adresi.
    """
    title = dokuman.baslik or f"Doküman #{dokuman.pk}"

    lines: List[str] = []
    lines += [f"# {title}", ""]
    lines += [f"- Durum: {dokuman.durum}", f"- Oluşturulma: {dokuman.created_at}", ""]

    # Parçaları ekle (kısa)
    try:
        parcalar = dokuman.parcalar.all().order_by("sira")[:50]
        if parcalar:
            lines += ["## Parçalar (ilk 50)", ""]
            for p in parcalar:
                addr = getattr(p, "adres", "") or ""
                z = getattr(p, "zorluk", "") or ""
                zs = getattr(p, "zorluk_skoru", 0.0)
                metin = (p.metin or "").strip().replace("\n", " ")
                if len(metin) > 120:
                    metin = metin[:120] + "…"
                lines.append(f"- [{p.sira}] ({z}:{zs:.2f}) {addr} — {metin}")
            lines.append("")
    except Exception:
        # Parçalar ilişkisi yoksa vs. düşmesin
        pass

    out = "\n".join(lines).strip() + "\n"
    MAX_CHARS = 500_000
    if len(out) > MAX_CHARS:
        out = out[:MAX_CHARS] + "\n\n> [TRUNCATED]\n"
    return out


def render_cheatsheet(dokuman, fmt: str) -> RenderResult:
    md = build_cheatsheet_markdown(dokuman)
    base_name = f"cheatsheet_{dokuman.pk}"

    if fmt == "md":
        return RenderResult(
            content=md.encode("utf-8"),
            content_type="text/markdown; charset=utf-8",
            filename=f"{base_name}.md",
        )

    if fmt == "pdf":
        # Import burada → reportlab yoksa server düşmez
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from io import BytesIO
        except Exception as e:
            raise ExportError("PDF export için 'reportlab' gerekli. Kur: pip install reportlab") from e

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4

        y = height - 50
        c.setFont("Helvetica", 11)

        for line in md.splitlines():
            if y < 50:
                c.showPage()
                c.setFont("Helvetica", 11)
                y = height - 50
            c.drawString(50, y, line[:140])
            y -= 14

        c.save()
        pdf_bytes = buf.getvalue()
        buf.close()

        return RenderResult(
            content=pdf_bytes,
            content_type="application/pdf",
            filename=f"{base_name}.pdf",
        )

    if fmt == "docx":
        try:
            from docx import Document
            from io import BytesIO
        except Exception as e:
            raise ExportError("DOCX export için 'python-docx' gerekli. Kur: pip install python-docx") from e

        doc = Document()
        for line in md.splitlines():
            doc.add_paragraph(line)

        buf = BytesIO()
        doc.save(buf)
        data = buf.getvalue()
        buf.close()

        return RenderResult(
            content=data,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"{base_name}.docx",
        )

    raise ExportError("format geçersiz (md/pdf/docx)")


def mark_processing(export_obj):
    export_obj.status = "processing"
    export_obj.started_at = timezone.now()
    export_obj.hata = None
    export_obj.save(update_fields=["status", "started_at", "hata"])


def mark_failed(export_obj, err: str):
    export_obj.status = "failed"
    export_obj.hata = err
    export_obj.finished_at = timezone.now()
    export_obj.save(update_fields=["status", "hata", "finished_at"])


def mark_done(export_obj):
    export_obj.status = "done"
    export_obj.finished_at = timezone.now()
    export_obj.save(update_fields=["status", "finished_at"])