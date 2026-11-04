"""Celery tasks for lumina Django app."""

from celery import shared_task


@shared_task
def cleanup_expired_files_task():
    """Celery beat task untuk cleanup file uploads yang expired atau duplicated."""
    from django.core.management import call_command

    call_command("cleanup_expired_files")
