"""
views.py — API views for the ingest pipeline.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework.views import APIView

from .serializers import IngestUploadSerializer
from .services import _log_ingest
from .tasks import run_ingest_pipeline_task
from core.models import IngestLog, Document as DocumentModel


class IngestStatusView(APIView):
    """
    GET /api/ingest/status/{document_id}/
    Polling endpoint untuk status dan log ingest.
    Query params:
    - session: session_id untuk menyekat log sesi
    - after: last_log_id untuk ambil log baru saja
    """

    authentication_classes = [*APIView.authentication_classes]
    permission_classes = [IsAuthenticated]

    def get(self, request, document_id: int, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.role == "admin"):
            return Response(
                {"detail": "Anda tidak memiliki izin untuk melihat status ingest."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            document = DocumentModel.objects.get(pk=document_id)
        except DocumentModel.DoesNotExist:
            return Response(
                {"detail": "Dokumen tidak ditemukan."},
                status=status.HTTP_404_NOT_FOUND,
            )

        session_id = request.query_params.get("session")
        after_id = int(request.query_params.get("after", 0))

        log_query = IngestLog.objects.filter(document_id=document_id, id__gt=after_id).order_by("id")
        if session_id:
            log_query = log_query.filter(session_id=session_id)

        logs = [
            {
                "id": log.id,
                "step": log.step,
                "status": log.status,
                "message": log.message,
                "error_message": log.error_message,
                "metadata": log.metadata,
                "created_at": log.created_at.isoformat(),
            }
            for log in log_query
        ]

        return Response(
            {
                "logs": logs,
                "status": document.status,
            }
        )


class IngestViewSet(ViewSet):
    """
    ViewSet untuk re-ingest dokumen.
    """

    authentication_classes = [*ViewSet.authentication_classes]
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=["post"], url_path="re-ingest")
    def re_ingest(self, request, pk=None):
        """Trigger re-ingest untuk dokumen yang sudah ada."""
        if not (request.user.is_authenticated and request.user.role == "admin"):
            return Response(
                {"detail": "Anda tidak memiliki izin untuk melakukan re-ingest."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            document = DocumentModel.objects.get(pk=pk)
        except DocumentModel.DoesNotExist:
            return Response(
                {"detail": "Dokumen tidak ditemukan."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if document.status == "processing":
            return Response(
                {"detail": "Dokumen sedang diproses, coba lagi nanti."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session_id = str(uuid.uuid4())

        _log_ingest(document.id, "re-init", f"Re-ingest dimulai, document_id={pk}", session_id)

        run_ingest_pipeline_task.delay(
            file_path=document.path_file,
            original_filename=document.document_name,
            document_id=document.id,
            user_id=request.user.id,
            session_id=session_id,
        )

        return Response(
            {
                "message": "Re-ingest berhasil dimulai.",
                "document_id": document.id,
                "session_id": session_id,
                "status": "processing",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class IngestUploadView(APIView):
    """
    POST /api/ingest/upload/
    Accepts a multipart file upload, creates/updates a Document record,
    immediately marks it as processing, then triggers the ingest pipeline asynchronously.
    """

    authentication_classes = [*APIView.authentication_classes]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = "upload"

    def post(self, request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.role == "admin"):
            return Response(
                {"detail": "Anda tidak memiliki izin untuk mengunggah dokumen."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # APIView checks throttles once before dispatching this handler.

        serializer = IngestUploadSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data["document"]
        document_id = serializer.validated_data.get("document_id")

        suffix = Path(file.name).suffix.lower()

        upload_dir = Path(settings.MEDIA_ROOT) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_filename = f"{uuid.uuid4()}{suffix}"
        dest_path = upload_dir / safe_filename
        with open(dest_path, "wb+") as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        session_id = str(uuid.uuid4())

        if document_id is None:
            document = DocumentModel.objects.create(
                user_id=request.user.id,
                document_name=file.name,
                path_file=str(dest_path),
                file_type=suffix.lstrip(".").lower(),
                size=file.size,
                status=DocumentModel.Status.PROCESSING,
                ingest_session_id=session_id,
            )
            _log_ingest(document.id, "init", f"Upload baru: {file.name}", session_id)
        else:
            DocumentModel.objects.filter(pk=document_id).update(
                document_name=file.name,
                path_file=str(dest_path),
                file_type=suffix.lstrip(".").lower(),
                size=file.size,
                status=DocumentModel.Status.PROCESSING,
                ingest_session_id=session_id,
                updated_at=timezone.now(),
            )
            document = DocumentModel.objects.get(pk=document_id)
            _log_ingest(document.id, "re-init", f"Re-ingest dimulai, document_id={document_id}", session_id)

        run_ingest_pipeline_task.delay(
            file_path=str(dest_path),
            original_filename=file.name,
            document_id=document.id,
            user_id=request.user.id,
            session_id=session_id,
        )

        return Response(
            {
                "message": "Dokumen berhasil diupload dan sedang diproses.",
                "document_id": document.id,
                "session_id": session_id,
                "status": "processing",
            },
            status=status.HTTP_202_ACCEPTED,
        )
