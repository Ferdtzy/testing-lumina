from pathlib import Path

from celery import shared_task

from .services import run_ingest_pipeline


@shared_task(bind=True, autoretry_for=(), max_retries=0)
def run_ingest_pipeline_task(
    self,
    file_path: str,
    original_filename: str,
    document_id: int,
    user_id: int,
    session_id: str,
) -> dict:
    return run_ingest_pipeline(
        file_path=Path(file_path),
        original_filename=original_filename,
        document_id=document_id,
        user_id=user_id,
        session_id=session_id,
    )
