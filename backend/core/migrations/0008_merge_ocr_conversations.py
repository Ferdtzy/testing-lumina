from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_chunk_metadata"),
        ("core", "0007_backfill_conversation_ids"),
    ]
    operations = []
