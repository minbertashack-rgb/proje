from django.core.management.base import BaseCommand

from dokuman.models import Dokuman
from dokuman.services.rag import sil_dokuman_indexi, upsert_dokuman_parcalari


class Command(BaseCommand):
    help = "Mevcut doküman parçalarını Chroma'ya yeniden indexler."

    def add_arguments(self, parser):
        parser.add_argument("--doc-id", type=int, default=None)

    def handle(self, *args, **options):
        doc_id = options.get("doc_id")

        qs = Dokuman.objects.all().order_by("id")
        if doc_id is not None:
            qs = qs.filter(id=doc_id)

        total_docs = 0
        total_chunks = 0

        for doc in qs:
            sil_dokuman_indexi(doc.id)
            count = upsert_dokuman_parcalari(doc)

            total_docs += 1
            total_chunks += count
            self.stdout.write(self.style.SUCCESS(
                f"dokuman={doc.id} | indexed={count}"
            ))

        self.stdout.write(self.style.SUCCESS(
            f"TAMAM | dokuman_sayisi={total_docs} | toplam_parca={total_chunks}"
        ))
