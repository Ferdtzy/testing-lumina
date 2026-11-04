from rest_framework import serializers, pagination
from django.core.files.uploadedfile import UploadedFile

from core.models import Document, Chunk, IngestLog


class DocumentPagination(pagination.PageNumberPagination):
    page_size = 10
    page_size_query_param = "limit"
    max_page_size = 100


class DocumentUploadSerializer(serializers.Serializer):
    document = serializers.FileField(error_messages={"required": "Pilih dokumen terlebih dahulu.", "empty": "File kosong tidak dapat diunggah."})

    def validate_document(self, value: UploadedFile) -> UploadedFile:
        from pathlib import Path
        if Path(value.name).suffix.lower() not in {".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}:
            raise serializers.ValidationError("Tipe file tidak didukung.")
        if value.size > 100 * 1024 * 1024:
            raise serializers.ValidationError("Ukuran file melebihi batas 100 MB.")
        return value


class DocumentSerializer(serializers.ModelSerializer):
    """Serializer untuk model Document."""

    size_human = serializers.SerializerMethodField()
    user_username = serializers.CharField(source="user.username", read_only=True)
    total_chunk_count = serializers.IntegerField(read_only=True, default=0)
    document_text_chunk_count = serializers.IntegerField(read_only=True, default=0)
    ocr_chunk_count = serializers.IntegerField(read_only=True, default=0)
    vision_chunk_count = serializers.IntegerField(read_only=True, default=0)
    unclassified_chunk_count = serializers.SerializerMethodField()
    processed_page_count = serializers.IntegerField(read_only=True, default=0)
    processing_duration_seconds = serializers.SerializerMethodField()
    chunk_count = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "user",
            "user_username",
            "document_name",
            "path_file",
            "file_type",
            "size",
            "size_human",
            "status",
            "is_ocr",
            "ingest_session_id",
            "total_chunk_count",
            "document_text_chunk_count",
            "ocr_chunk_count",
            "vision_chunk_count",
            "unclassified_chunk_count",
            "processed_page_count",
            "processing_duration_seconds",
            "created_at",
            "updated_at",
            "deleted_at",
            "chunk_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "deleted_at"]

    def get_size_human(self, obj: Document) -> str:
        """Mengembalikan ukuran file dalam format human-readable."""
        bytes_size = obj.size
        if bytes_size < 1024:
            return f"{bytes_size} B"
        if bytes_size < 1048576:
            return f"{round(bytes_size / 1024, 1)} KB"
        return f"{round(bytes_size / 1048576, 1)} MB"

    def get_processing_duration_seconds(self, obj: Document) -> int | None:
        """Durasi dari dokumen dibuat sampai pembaruan status terakhir."""
        if not obj.created_at or not obj.updated_at:
            return None
        return max(0, round((obj.updated_at - obj.created_at).total_seconds()))

    def get_unclassified_chunk_count(self, obj: Document) -> int:
        """Chunk lama yang dibuat sebelum metadata provenance tersedia."""
        classified = (
            getattr(obj, "document_text_chunk_count", 0)
            + getattr(obj, "ocr_chunk_count", 0)
            + getattr(obj, "vision_chunk_count", 0)
        )
        return max(0, getattr(obj, "total_chunk_count", 0) - classified)
    def get_chunk_count(self, obj: Document) -> int:
        """Mengembalikan jumlah chunk untuk dokumen ini."""
        return obj.chunks.filter(deleted_at__isnull=True).count()


class ChunkSerializer(serializers.ModelSerializer):
    """Serializer untuk model Chunk."""

    class Meta:
        model = Chunk
        fields = [
            "id",
            "document",
            "chunk_text",
            "page",
            "metadata",
            "created_at",
            "updated_at",
            "deleted_at",
        ]
        read_only_fields = ["id", "page", "metadata", "created_at", "updated_at", "deleted_at"]


class IngestLogSerializer(serializers.ModelSerializer):
    """Serializer untuk model IngestLog."""

    class Meta:
        model = IngestLog
        fields = [
            "id",
            "document",
            "session_id",
            "step",
            "status",
            "message",
            "error_message",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
