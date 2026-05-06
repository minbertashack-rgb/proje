from django.db import migrations, models
import django.db.models.deletion


def forwards(apps, schema_editor):
    Not = apps.get_model("dokuman", "Not")
    Parca = apps.get_model("dokuman", "Parca")

    # 1) dokuman NULL olan notları parça üzerinden doldur
    for n in Not.objects.filter(dokuman__isnull=True).exclude(parca__isnull=True):
        try:
            p = Parca.objects.get(id=n.parca_id)
        except Parca.DoesNotExist:
            continue
        n.dokuman_id = p.dokuman_id
        n.save(update_fields=["dokuman"])

    # 2) hâlâ NULL kalanları sil (parçası da yoksa zaten bağlayamayız)
    Not.objects.filter(dokuman__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("dokuman", "0008_rename_icerik_not_metin_alter_not_dokuman"),  # <-- BURAYI SENDEKİ EN SON MIGRATION ADIYLA DEĞİŞTİR
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),

        migrations.AlterField(
            model_name="not",
            name="dokuman",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notlar",
                to="dokuman.dokuman",
            ),
        ),
    ]