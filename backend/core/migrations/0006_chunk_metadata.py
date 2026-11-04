from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_merge_ocr_ingest_logs"),
    ]

    operations = [
        migrations.AddField(
            model_name="chunk",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
