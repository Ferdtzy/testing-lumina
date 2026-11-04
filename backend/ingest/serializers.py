"""
serializers.py — DRF serializers for the ingest pipeline.
"""

import logging
import mimetypes
from pathlib import Path

from rest_framework import serializers

from core.models import Document as DocumentModel

logger = logging.getLogger(__name__)


class IngestUploadSerializer(serializers.Serializer):
    """Serializer untuk upload dokumen dengan validasi."""

    document = serializers.FileField(required=True)
    document_id = serializers.IntegerField(required=False, allow_null=True)

    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    MAX_SIZE_KB = 102400  # 100 MB
    ALLOWED_MIME_TYPES = {
        ".jpg": {"image/jpeg"},
        ".jpeg": {"image/jpeg"},
        ".png": {"image/png"},
        ".bmp": {"image/bmp", "image/x-ms-bmp"},
        ".tiff": {"image/tiff"},
        ".webp": {"image/webp"},
        ".pdf": {"application/pdf", "application/x-pdf"},
        ".docx": {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",
            "application/x-zip-compressed",
            "application/octet-stream",
        },
        ".txt": {"text/plain", "text/csv", "application/octet-stream"},
    }

    def validate_document(self, value):
        """Validasi extension, mime type, dan ukuran file."""
        suffix = Path(value.name).suffix.lower()

        if suffix not in self.ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"Tipe file tidak didukung: {suffix}"
            )

        if value.size and value.size > self.MAX_SIZE_KB * 1024:
            raise serializers.ValidationError(
                "Ukuran file melebihi batas 100 MB."
            )

        # Read the first few bytes for header signature verification
        initial_bytes = b""
        try:
            for chunk in value.chunks():
                initial_bytes = chunk[:2048]
                break
        except Exception:
            pass

        # Try MIME type detection with python-magic if available
        magic_verified = False
        try:
            import magic
            from tempfile import NamedTemporaryFile

            temp_path = None
            try:
                with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    for chunk in value.chunks():
                        tmp.write(chunk)
                    temp_path = tmp.name

                raw_mime = magic.from_file(temp_path, mime=True)
                mime_type = raw_mime.split(";")[0].strip().lower() if raw_mime else ""
                allowed = self.ALLOWED_MIME_TYPES.get(suffix, set())

                if mime_type in allowed or (suffix == ".txt" and mime_type.startswith("text/")):
                    magic_verified = True
                else:
                    raise serializers.ValidationError(
                        f"MIME type tidak sesuai untuk file {suffix}. Terdeteksi: {raw_mime}"
                    )
            finally:
                if temp_path and Path(temp_path).exists():
                    Path(temp_path).unlink()
        except ImportError:
            logger.warning("python-magic tidak tersedia, menggunakan fallback validasi signature byte dan mimetypes.")
        except serializers.ValidationError:
            raise
        except Exception as err:
            logger.warning("Error saat deteksi MIME dengan python-magic: %s, menggunakan fallback.", err)

        # Fallback header signature / magic bytes validation if python-magic not installed or bypassed
        if not magic_verified:
            if suffix == ".pdf" and not initial_bytes.startswith(b"%PDF"):
                raise serializers.ValidationError("Konten file bukan PDF yang valid.")
            elif suffix == ".docx" and not initial_bytes.startswith(b"PK\x03\x04"):
                raise serializers.ValidationError("Konten file bukan dokumen Word (.docx) yang valid.")

        if suffix in {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}:
            from PIL import Image, UnidentifiedImageError

            try:
                value.seek(0)
                with Image.open(value) as image:
                    image.verify()
            except (UnidentifiedImageError, OSError, ValueError) as exc:
                raise serializers.ValidationError("Konten file bukan gambar yang valid.") from exc
        value.seek(0)
        return value

    def validate_document_id(self, value):
        """Validasi document_id jika dikirim."""
        if value is None:
            return value

        try:
            document_id = int(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError(
                "document_id harus berupa integer."
            )

        # Check existence
        try:
            existing = DocumentModel.objects.get(pk=document_id)
        except DocumentModel.DoesNotExist:
            raise serializers.ValidationError(
                "Dokumen tidak ditemukan."
            )

        self.existing_document = existing
        return document_id

    def validate(self, attrs):
        """Validasi ownership jika document_id dikirim."""
        document_id = attrs.get("document_id")
        user = self.context.get("request").user if self.context.get("request") else None

        if document_id is not None and user is not None:
            if self.existing_document.user_id != user.id:
                raise serializers.ValidationError(
                    "Anda tidak memiliki akses untuk re-ingest dokumen ini."
                )

        return attrs
