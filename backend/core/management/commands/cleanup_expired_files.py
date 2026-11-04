"""
cleanup_expired_files.py — Django management command untuk cleanup file uploads.

Task LUMINA-6: Cleanup file uploads & retention media/uploads

Fungsi:
1. Hapus file di media/uploads/{uuid} setelah _embed_and_persist sukses
2. Hapus file >7 hari jika status=failed
3. Deduplikasi documents/ via sha256 (skip re-embed jika hash sama)
"""

import hashlib
import shutil
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from core.models import Document
from ingest import config


class Command(BaseCommand):
    help = "Cleanup expired uploads and deduplicate documents"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Tampilkan file yang akan dihapus tanpa benar-benar menghapus",
        )
        parser.add_argument(
            "--expired-only",
            action="store_true",
            help="Hanya cleanup file expired (>7 hari, status=failed)",
        )
        parser.add_argument(
            "--dedupe-only",
            action="store_true",
            help="Hanya deduplikasi documents/",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        expired_only = options["expired_only"]
        dedupe_only = options["dedupe_only"]

        self.stdout.write(self.style.WARNING(f"Dry run: {dry_run}"))

        if not dedupe_only:
            self._cleanup_expired_files(dry_run)

        if not expired_only:
            self._deduplicate_documents(dry_run)

        self.stdout.write(self.style.SUCCESS("Cleanup selesai"))

    def _cleanup_expired_files(self, dry_run: bool):
        """Hapus file upload yang expired atau berhasil di-embed."""
        uploads_dir = config.BASE_DIR / "media" / "uploads"

        if not uploads_dir.exists():
            self.stdout.write(self.style.WARNING("No uploads directory found"))
            return

        now = timezone.now()
        threshold = now - timedelta(days=7)

        files_to_delete = []

        for file_path in uploads_dir.glob("*"):
            if not file_path.is_file():
                continue

            stat = file_path.stat()
            file_mtime = timezone.localtime(timezone.datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc))

            doc = Document.objects.filter(path_file__contains=file_path.name).first()

            if doc:
                if doc.status == Document.Status.FAILED and file_mtime < threshold:
                    files_to_delete.append((file_path, file_mtime, "failed > 7 hari"))
                elif doc.status == Document.Status.INDEXED:
                    files_to_delete.append((file_path, file_mtime, "sukses ingest"))
            else:
                if file_mtime < threshold:
                    files_to_delete.append((file_path, file_mtime, "orphan > 7 hari"))

        self.stdout.write(f"Found {len(files_to_delete)} file(s) to delete")

        for file_path, mtime, reason in files_to_delete:
            self.stdout.write(f"  - {file_path.name} ({mtime:%Y-%m-%d %H:%M}) - {reason}")
            if not dry_run:
                try:
                    file_path.unlink()
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"    Gagal hapus {file_path.name}: {exc}"))

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: tidak ada file yang dihapus"))

    def _deduplicate_documents(self, dry_run: bool):
        """Deduplikasi file di documents/ berdasarkan SHA256 hash."""
        documents_dir = config.DOCUMENTS_DIR

        if not documents_dir.exists():
            self.stdout.write(self.style.WARNING("No documents directory found"))
            return

        hash_to_files: dict[str, list[Path]] = {}

        for file_path in documents_dir.glob("*"):
            if not file_path.is_file():
                continue

            file_hash = self._compute_sha256(file_path)
            if file_hash:
                hash_to_files.setdefault(file_hash, []).append(file_path)

        duplicates_found = sum(len(files) - 1 for files in hash_to_files.values() if len(files) > 1)
        self.stdout.write(f"Found {duplicates_found} duplicate file(s)")

        for file_hash, files in hash_to_files.items():
            if len(files) <= 1:
                continue

            files.sort(key=lambda p: p.stat().st_ctime)
            original = files[0]
            duplicates = files[1:]

            self.stdout.write(f"Original: {original.name}")
            for dup in duplicates:
                doc = Document.objects.filter(path_file__contains=dup.name).first()
                if doc:
                    if not dry_run:
                        doc.path_file = str(original)
                        doc.save(update_fields=["path_file", "updated_at"])
                        try:
                            dup.unlink()
                            self.stdout.write(self.style.SUCCESS(f"  - Removed duplicate: {dup.name}"))
                        except Exception as exc:
                            self.stderr.write(self.style.ERROR(f"    Gagal hapus {dup.name}: {exc}"))
                    else:
                        self.stdout.write(f"  - Would remove duplicate: {dup.name}")
                else:
                    if not dry_run:
                        try:
                            dup.unlink()
                            self.stdout.write(self.style.SUCCESS(f"  - Removed orphan duplicate: {dup.name}"))
                        except Exception as exc:
                            self.stderr.write(self.style.ERROR(f"    Gagal hapus {dup.name}: {exc}"))
                    else:
                        self.stdout.write(f"  - Would remove orphan duplicate: {dup.name}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: tidak ada file yang dihapus"))

    def _compute_sha256(self, file_path: Path) -> str | None:
        """Compute SHA256 hash of a file."""
        try:
            hasher = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Gagal compute hash {file_path.name}: {exc}"))
            return None
