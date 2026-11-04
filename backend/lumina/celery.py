import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lumina.settings")

app = Celery("lumina")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "cleanup-daily": {
        "task": "core.tasks.cleanup_expired_files_task",
        "schedule": crontab(hour=3, minute=0, day_of_week="monday"),
    },
}
