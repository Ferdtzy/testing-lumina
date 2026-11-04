import logging
import uuid
from uuid import uuid4
from pathlib import Path
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from core.models import Document, Chunk, IngestLog
from .serializers import DocumentSerializer, ChunkSerializer, IngestLogSerializer, DocumentPagination

logger = logging.getLogger(__name__)


class DocumentViewSet(viewsets.ModelViewSet):
    """ViewSet untuk CRUD dokumen."""

    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = DocumentPagination

    def get_queryset(self):
        """Filter dokumen berdasarkan user yang sedang login."""
        user = self.request.user
        if user.role == "admin":
            queryset = Document.objects.filter(deleted_at__isnull=True)
        else:
            queryset = Document.objects.filter(
                user=user,
                deleted_at__isnull=True,
            )
        active_chunks = Q(chunks__deleted_at__isnull=True)
        return queryset.annotate(
            total_chunk_count=Count("chunks", filter=active_chunks),
            document_text_chunk_count=Count(
                "chunks",
                filter=active_chunks & Q(chunks__metadata__source_type="document_text"),
            ),
            ocr_chunk_count=Count(
                "chunks",
                filter=active_chunks & Q(chunks__metadata__source_type="ocr"),
            ),
            vision_chunk_count=Count(
                "chunks",
                filter=active_chunks & Q(chunks__metadata__source_type="vision"),
            ),
            processed_page_count=Count(
                "chunks__page",
                filter=active_chunks & Q(chunks__page__isnull=False),
                distinct=True,
            ),
        ).order_by("-created_at")

    parser_classes = [MultiPartParser, FormParser]

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """Mengembalikan ringkasan statistik dokumen (admin only)."""
        if not (request.user.is_authenticated and request.user.role == "admin"):
            return Response(
                {"detail": "Anda tidak memiliki izin untuk melihat ringkasan dokumen."},
                status=status.HTTP_403_FORBIDDEN,
            )

        total_count = Document.objects.filter(deleted_at__isnull=True).count()
        indexed_count = Document.objects.filter(
            deleted_at__isnull=True,
            status__in=["indexed", "completed", "success"],
        ).count()
        processing_count = Document.objects.filter(
            deleted_at__isnull=True,
            status__in=["processing", "pending"],
        ).count()
        failed_count = Document.objects.filter(
            deleted_at__isnull=True,
            status__in=["failed", "error"],
        ).count()

        return Response(
            {
                "total": total_count,
                "indexed": indexed_count,
                "processing": processing_count,
                "failed": failed_count,
            },
            status=status.HTTP_200_OK,
        )

    def create(self, request, *args, **kwargs):
        """Handle multipart file upload — simpan file, buat Document, jalankan ingest async."""
        from .serializers import DocumentUploadSerializer
        upload = DocumentUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        file = upload.validated_data["document"]
        if not file:
            return Response(
                {"detail": "Field 'document' (file) is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        suffix = file.name.rsplit(".", 1)[-1].lower()
        upload_dir = Path(settings.MEDIA_ROOT) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_filename = f"{uuid4()}.{suffix}"
        dest_path = upload_dir / safe_filename
        with open(dest_path, "wb+") as dest:
            for chunk in file.chunks():
                dest.write(chunk)
        session_id = str(uuid4())
        image_ext = {"jpg", "jpeg", "png", "bmp", "tiff", "webp"}
        is_ocr = suffix in image_ext
        document = Document.objects.create(
            user=request.user,
            document_name=file.name,
            path_file=str(dest_path),
            file_type=suffix,
            size=file.size,
            status=Document.Status.PROCESSING,
            ingest_session_id=session_id,
            is_ocr=is_ocr,
        )
        from ingest.services import run_ingest_pipeline
        import threading
        def _run_async():
            try:
                run_ingest_pipeline(
                    file_path=dest_path,
                    original_filename=file.name,
                    document_id=document.id,
                    user_id=request.user.id,
                    session_id=session_id,
                )
            except Exception as e:
                logger.error("Ingest pipeline failed (async): %s", e)
                document.status = Document.Status.FAILED
                document.save(update_fields=["status"])
        threading.Thread(target=_run_async, daemon=True).start()
        return Response(
            {"message": "Dokumen berhasil diupload dan sedang diproses.", "document_id": document.id, "session_id": session_id, "status": "processing"},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def ingest(self, request, pk=None):
        """Trigger ingest pipeline untuk dokumen ini."""
        document = self.get_object()
        if document.status == "indexed":
            return Response({"detail": "Dokumen sudah terindeks."}, status=status.HTTP_200_OK)
        document.status = Document.Status.PROCESSING
        document.save(update_fields=["status"])
        from ingest.services import run_ingest_pipeline
        import threading
        def _run():
            try:
                run_ingest_pipeline(
                    file_path=Path(document.path_file),
                    original_filename=document.document_name,
                    document_id=document.id,
                    user_id=document.user_id,
                    session_id=document.ingest_session_id,
                )
            except Exception as e:
                from core.models import IngestLog
                IngestLog.objects.create(
                    document_id=document.id,
                    session_id=document.ingest_session_id,
                    step="error",
                    message=str(e),
                )
                document.status = Document.Status.FAILED
                document.save(update_fields=["status"])
        threading.Thread(target=_run, daemon=True).start()
        return Response({"detail": "Ingest dimulai.", "status": "processing"})

    @action(detail=True, methods=["delete"])
    def delete(self, request, pk=None):
        """Hapus dokumen secara lunak (soft delete)."""
        document = self.get_object()
        document.deleted_at = timezone.now()
        document.save(update_fields=["deleted_at"])
        return Response({"detail": "Dokumen dihapus."})

    @action(detail=True, methods=["get"])
    def chunks(self, request, pk=None):
        """Mengembalikan daftar chunk untuk dokumen tertentu."""
        document = self.get_object()
        chunks = Chunk.objects.filter(
            document=document,
            deleted_at__isnull=True,
        ).order_by("page", "id")
        serializer = ChunkSerializer(chunks, many=True)
        return Response({"results": serializer.data})

    @action(detail=True, methods=["get"])
    def ingest_logs(self, request, pk=None):
        """Mengembalikan log ingest untuk dokumen tertentu."""
        try:
            document = self.get_queryset().get(pk=pk)
        except Document.DoesNotExist:
            return Response(
                {"detail": "Dokumen tidak ditemukan."},
                status=status.HTTP_404_NOT_FOUND,
            )
        logs = IngestLog.objects.filter(document=document).order_by("-created_at")
        serializer = IngestLogSerializer(logs, many=True)
        return Response({"results": serializer.data})

    def perform_create(self, serializer):
        """Set user_id otomatis dari user yang sedang login."""
        serializer.save(user=self.request.user)


class ChunkViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet read-only untuk chunk dokumen."""

    queryset = Chunk.objects.all()
    serializer_class = ChunkSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter chunk berdasarkan dokumen milik user."""
        user = self.request.user
        if user.role == "admin":
            return Chunk.objects.filter(deleted_at__isnull=True, document__deleted_at__isnull=True)
        return Chunk.objects.filter(document__user=user, deleted_at__isnull=True, document__deleted_at__isnull=True)


class IngestLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet read-only untuk log ingest."""

    queryset = IngestLog.objects.all()
    serializer_class = IngestLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter log berdasarkan dokumen milik user."""
        user = self.request.user
        if user.role == "admin":
            return IngestLog.objects.filter(document__deleted_at__isnull=True)
        return IngestLog.objects.filter(document__user=user, document__deleted_at__isnull=True)
