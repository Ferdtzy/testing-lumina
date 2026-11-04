from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_add_page_to_chunk"),
    ]

    operations = [
        migrations.AddField(
            model_name="ingestlog",
            name="error_message",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ingestlog",
            name="metadata",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ingestlog",
            name="status",
            field=models.CharField(
                choices=[("started", "Started"), ("success", "Success"), ("failed", "Failed")],
                default="started",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="ingestlog",
            index=models.Index(fields=["document", "step", "status"], name="core_ingest_doc_step_stat_idx"),
        ),
    ]
