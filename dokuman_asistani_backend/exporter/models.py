from django.conf import settings
from django.db import models
import uuid


class CheatSheetExport(models.Model):
    class Format(models.TextChoices):
        MD = "md", "Markdown"
        PDF = "pdf", "PDF"
        DOCX = "docx", "DOCX"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # SENDE Dokuman modeli "dokuman" app'inde:
    dokuman = models.ForeignKey(
        "dokuman.Dokuman",
        on_delete=models.CASCADE,
        related_name="exports",
    )

    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cheatsheet_exports",
    )

    format = models.CharField(max_length=10, choices=Format.choices, default=Format.MD)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    dosya = models.FileField(upload_to="exports/cheatsheet/", null=True, blank=True)
    hata = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["format"]),
        ]

    def __str__(self):
        return f"{self.id} ({self.format}) {self.status}"