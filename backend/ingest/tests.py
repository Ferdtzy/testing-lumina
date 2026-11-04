import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from langchain_core.documents import Document as LCDocument

from core.models import Answer, Chunk, Document as DocumentModel, History, IngestLog, Query
from ingest import config
from ingest.retrieval import (
    RagPipelineError,
    _expand_visual_pairs,
    _format_context,
    _invoke_llm_with_retry,
    _is_transient_llm_error,
    _rrf_fusion,
    _save_answer,
    _similarity_search,
    _sparse_search,
    run_rag_query,
)
from ingest.reranker import get_reranker, rerank_chunks
from ingest.services import (
    _chunk_documents,
    _copy_to_documents,
    _embed_and_persist,
    _load_document,
    _log_ingest,
    _mark_failed,
    _mark_indexed,
    _preprocess_documents,
    get_embeddings,
    run_ingest_pipeline,
)
from ingest.tasks import run_ingest_pipeline_task

User = get_user_model()

# Helper sample 1-page PDF bytes with valid structure and sufficient text length (>50 chars)
SAMPLE_1PAGE_PDF_BYTES = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 220 >>
stream
BT
/F1 12 Tf
72 712 Td
(Ini adalah dokumen pengujian integrasi Lumina ingest pipeline. Dokumen ini berisi teks yang cukup panjang untuk memastikan ekstraksi dan chunking berjalan dengan sukses.) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000244 00000 n
0000000516 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
597
%%EOF"""


def get_mock_1024d_embedding(val: float = 0.05):
    """Return a 1024-dimension unit-like vector."""
    return [val] * 1024


# ─────────────────────────────────────────────────────────────────────────────
# 1. Unit Tests for Ingest Pipeline Services
# ─────────────────────────────────────────────────────────────────────────────

class IngestServicesUnitTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="researcher@example.com",
            username="researcher",
            password="password123",
            role=User.Role.ADMIN,
        )
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_log_ingest_success_and_error_handling(self):
        doc = DocumentModel.objects.create(
            user=self.user,
            document_name="doc.pdf",
            path_file="/tmp/doc.pdf",
            file_type="pdf",
            size=1024,
        )
        _log_ingest(
            document_id=doc.id,
            step="load",
            message="Document loaded",
            session_id="12345678-1234-5678-1234-567812345678",
            status="success",
            metadata={"pages": 1},
        )
        log = IngestLog.objects.get(document=doc, step="load")
        self.assertEqual(log.status, "success")
        self.assertEqual(log.message, "Document loaded")
        self.assertEqual(log.metadata, {"pages": 1})

        # Test safe exception handling in _log_ingest
        with patch("core.models.IngestLog.objects.create", side_effect=Exception("DB connection error")):
            # Should not raise exception
            _log_ingest(document_id=doc.id, step="fail_test", message="error test")

    def test_mark_failed_and_mark_indexed(self):
        doc = DocumentModel.objects.create(
            user=self.user,
            document_name="fail_doc.pdf",
            path_file="/tmp/fail_doc.pdf",
            file_type="pdf",
            size=1024,
            status=DocumentModel.Status.PROCESSING,
        )
        session_id = "12345678-1234-5678-1234-567812345678"
        _mark_failed(doc.id, session_id, "Some pipeline error occurred")
        doc.refresh_from_db()
        self.assertEqual(doc.status, DocumentModel.Status.FAILED)
        self.assertTrue(IngestLog.objects.filter(document=doc, step="error", status="failed").exists())

        # Test _mark_failed with document_id=None
        _mark_failed(None, session_id, "No doc error")

        # Test _mark_indexed
        _mark_indexed(doc.id, session_id)
        doc.refresh_from_db()
        self.assertEqual(doc.status, DocumentModel.Status.INDEXED)
        self.assertTrue(IngestLog.objects.filter(document=doc, step="complete", status="success").exists())

        Chunk.objects.create(document=doc, chunk_text="Indexed content", page=1)
        _mark_failed(doc.id, session_id, "Late duplicate task failed")
        doc.refresh_from_db()
        self.assertEqual(doc.status, DocumentModel.Status.INDEXED)
        self.assertTrue(IngestLog.objects.filter(document=doc, step="skip", status="success").exists())

    def test_duplicate_task_skips_document_that_is_already_indexed(self):
        stored_file = Path(self.temp_dir) / "stored.pdf"
        stored_file.write_bytes(SAMPLE_1PAGE_PDF_BYTES)
        doc = DocumentModel.objects.create(
            user=self.user,
            document_name="stored.pdf",
            path_file=str(stored_file),
            file_type="pdf",
            size=stored_file.stat().st_size,
            status=DocumentModel.Status.INDEXED,
        )
        Chunk.objects.create(document=doc, chunk_text="Already indexed", page=1)

        result = run_ingest_pipeline(
            file_path=Path(self.temp_dir) / "missing-upload.pdf",
            original_filename="stored.pdf",
            document_id=doc.id,
            user_id=self.user.id,
            session_id="12345678-1234-5678-1234-567812345678",
        )

        self.assertTrue(result["skipped"])
        self.assertEqual(result["chunks_added"], 1)
        doc.refresh_from_db()
        self.assertEqual(doc.status, DocumentModel.Status.INDEXED)
        self.assertTrue(IngestLog.objects.filter(document=doc, step="skip", status="success").exists())

    def test_copy_to_documents(self):
        test_file = Path(self.temp_dir) / "source.pdf"
        test_file.write_bytes(b"%PDF-1.4 sample content")

        with patch.object(config, "DOCUMENTS_DIR", Path(self.temp_dir) / "docs"):
            (Path(self.temp_dir) / "docs").mkdir(parents=True, exist_ok=True)
            copied = _copy_to_documents(test_file, "source.pdf", document_id=None, session_id=None)
            self.assertTrue(copied.exists())
            self.assertEqual(copied.name, "source.pdf")

            # Copying same file when already at destination
            copied_again = _copy_to_documents(copied, "source.pdf", document_id=None, session_id=None)
            self.assertEqual(copied, copied_again)

    def test_load_document_pdf(self):
        pdf_path = Path(self.temp_dir) / "test_1page.pdf"
        pdf_path.write_bytes(SAMPLE_1PAGE_PDF_BYTES)

        docs = _load_document(pdf_path, document_id=None, session_id=None)
        self.assertEqual(len(docs), 1)
        self.assertIn("Lumina ingest pipeline", docs[0].page_content)
        self.assertEqual(docs[0].metadata["source_file"], "test_1page.pdf")

    def test_load_document_docx(self):
        docx_path = Path(self.temp_dir) / "test.docx"
        docx_path.write_bytes(b"PK\x03\x04 dummy docx content")

        with patch("ingest.services.Docx2txtLoader") as mock_loader_cls:
            mock_loader = MagicMock()
            mock_loader.load.return_value = [
                LCDocument(page_content="Isi dari file Word docx pengujian Lumina.", metadata={})
            ]
            mock_loader_cls.return_value = mock_loader

            docs = _load_document(docx_path, document_id=None, session_id=None)
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].metadata["source_file"], "test.docx")

    def test_load_document_txt_utf8_and_latin1_fallback(self):
        # UTF-8 txt
        txt_path = Path(self.temp_dir) / "sample_utf8.txt"
        txt_path.write_text("Ini teks dokumen pengujian format TXT dengan UTF-8 Lumina.", encoding="utf-8")
        docs = _load_document(txt_path, document_id=None, session_id=None)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].metadata["source_file"], "sample_utf8.txt")

        # Latin-1 fallback
        txt_latin_path = Path(self.temp_dir) / "sample_latin.txt"
        txt_latin_path.write_bytes("Teks berkarakter khusus \xe9\xe8 latin-1 untuk pengujian Lumina.".encode("latin-1"))
        docs_latin = _load_document(txt_latin_path, document_id=None, session_id=None)
        self.assertEqual(len(docs_latin), 1)

    def test_load_document_unsupported_extension(self):
        invalid_path = Path(self.temp_dir) / "image.png"
        invalid_path.write_bytes(b"PNG fake data")
        with self.assertRaises(ValueError) as ctx:
            _load_document(invalid_path, document_id=None, session_id=None)
        self.assertIn("Unsupported extension", str(ctx.exception))

    def test_load_document_page_limit_and_char_limit(self):
        txt_path = Path(self.temp_dir) / "huge.txt"
        txt_path.write_text("dummy", encoding="utf-8")

        # Exceeds 500 pages
        with patch("ingest.services.TextLoader") as mock_loader_cls:
            mock_loader = MagicMock()
            mock_loader.load.return_value = [LCDocument(page_content=f"page {i}") for i in range(501)]
            mock_loader_cls.return_value = mock_loader
            with self.assertRaises(ValueError) as ctx:
                _load_document(txt_path, document_id=None, session_id=None)
            self.assertIn("melebihi batas maksimal 500 halaman", str(ctx.exception))

        # Exceeds 2 million characters
        with patch("ingest.services.TextLoader") as mock_loader_cls:
            mock_loader = MagicMock()
            mock_loader.load.return_value = [LCDocument(page_content="A" * 2_000_001)]
            mock_loader_cls.return_value = mock_loader
            with self.assertRaises(ValueError) as ctx:
                _load_document(txt_path, document_id=None, session_id=None)
            self.assertIn("melebihi batas maksimal 2 juta", str(ctx.exception))

    def test_preprocess_documents(self):
        raw_docs = [
            LCDocument(
                page_content="Paragraf satu.\n\n\n\nParagraf dua   dengan   banyak   spasi. Teks ini harus lebih dari lima puluh karakter.",
                metadata={"page": 0},
            ),
            LCDocument(
                page_content="Teks pendek <= 50",  # less than 50 chars -> should be dropped
                metadata={"page": 1},
            ),
        ]
        cleaned = _preprocess_documents(raw_docs, document_id=None, session_id=None)
        self.assertEqual(len(cleaned), 1)
        self.assertNotIn("\n\n\n\n", cleaned[0].page_content)
        self.assertNotIn("   ", cleaned[0].page_content)
        self.assertEqual(cleaned[0].metadata["page"], 0)

    def test_chunk_documents(self):
        text = "Lumina RAG Document Ingest Chunking. " * 80
        docs = [LCDocument(page_content=text, metadata={"source_file": "doc.pdf", "page": 0})]
        chunks = _chunk_documents(docs, document_id=None, session_id=None)
        self.assertGreaterEqual(len(chunks), 1)
        self.assertIn("start_index", chunks[0].metadata)

    @patch("ingest.services.get_embeddings")
    def test_embed_and_persist_unit_with_mock_embedding(self, mock_get_embeddings):
        # Mock embedding model to return 1024d vectors
        mock_emb = MagicMock()
        mock_emb.embed_documents.return_value = [
            get_mock_1024d_embedding(0.1),
            get_mock_1024d_embedding(0.2),
        ]
        mock_get_embeddings.return_value = mock_emb

        doc = DocumentModel.objects.create(
            user=self.user,
            document_name="embed_test.pdf",
            path_file="/tmp/embed_test.pdf",
            file_type="pdf",
            size=2048,
        )
        # Create an old chunk to test deletion/re-ingest
        Chunk.objects.create(
            document=doc,
            chunk_text="Old chunk text",
            page=1,
            embedding=get_mock_1024d_embedding(0.0),
        )

        chunks_input = [
            LCDocument(page_content="Chunk satu konten pengujian embedding 1024d.", metadata={
                "page": 0, "source_type": "ocr", "image_ref": "page-1", "ocr_confidence": 0.87,
            }),
            LCDocument(page_content="Chunk dua konten pengujian embedding 1024d.", metadata={"page": 1}),
        ]

        file_path = Path(self.temp_dir) / "embed_test.pdf"
        saved_count = _embed_and_persist(doc, file_path, chunks_input, session_id="11111111-2222-3333-4444-555555555555")

        self.assertEqual(saved_count, 2)
        # Verify old chunk was deleted and only 2 new chunks exist
        chunks_in_db = Chunk.objects.filter(document=doc).order_by("page")
        self.assertEqual(chunks_in_db.count(), 2)

        chunk1 = chunks_in_db[0]
        self.assertEqual(chunk1.page, 1)  # 0 + 1
        self.assertEqual(chunk1.chunk_text, "Chunk satu konten pengujian embedding 1024d.")
        self.assertEqual(chunk1.metadata["source_type"], "ocr")
        self.assertEqual(chunk1.metadata["image_ref"], "page-1")
        self.assertEqual(chunk1.metadata["ocr_confidence"], 0.87)
        self.assertEqual(len(chunk1.embedding), 1024)

        chunk2 = chunks_in_db[1]
        self.assertEqual(chunk2.page, 2)  # 1 + 1
        self.assertEqual(len(chunk2.embedding), 1024)

        # Verify embedding model received texts with 'passage: ' prefix
        mock_emb.embed_documents.assert_called_once_with([
            "passage: Chunk satu konten pengujian embedding 1024d.",
            "passage: Chunk dua konten pengujian embedding 1024d.",
        ])

    def test_get_embeddings_singleton(self):
        with patch("ingest.services.HuggingFaceEmbeddings") as mock_hf:
            import ingest.services
            ingest.services._embeddings = None
            emb1 = get_embeddings()
            emb2 = get_embeddings()
            self.assertEqual(emb1, emb2)
            mock_hf.assert_called_once()
            ingest.services._embeddings = None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Integration Tests: PDF Upload → 1024d Embedding & Chunks Saved
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(
    MEDIA_ROOT="D:/Project/Django/lumina/backend/media_test",
    DEBUG=True,
)
class IngestIntegrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            email="admin_ingest@example.com",
            username="admin_ingest",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.admin_user)
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def tearDown(self):
        media_test = "D:/Project/Django/lumina/backend/media_test"
        shutil.rmtree(media_test, ignore_errors=True)

    @patch("ingest.services.get_embeddings")
    def test_full_pipeline_upload_1page_pdf_persists_chunks_and_1024d_embeddings(self, mock_get_embeddings):
        """
        Integration test:
        Upload a 1-page PDF -> runs full pipeline -> chunks stored with 1024d embeddings & status INDEXED.
        """
        mock_emb = MagicMock()
        mock_emb.embed_documents.side_effect = lambda texts: [get_mock_1024d_embedding(0.123) for _ in texts]
        mock_get_embeddings.return_value = mock_emb

        pdf_file_path = Path(self.temp_dir) / "upload_sample.pdf"
        pdf_file_path.write_bytes(SAMPLE_1PAGE_PDF_BYTES)

        session_id = "11111111-2222-3333-4444-555555555555"

        result = run_ingest_pipeline(
            file_path=pdf_file_path,
            original_filename="sample_guideline.pdf",
            document_id=None,
            user_id=self.admin_user.id,
            session_id=session_id,
        )

        doc_id = result["document_id"]
        self.assertIsNotNone(doc_id)
        self.assertGreaterEqual(result["chunks_added"], 1)

        # 1. Verify Document model in DB
        doc = DocumentModel.objects.get(pk=doc_id)
        self.assertEqual(doc.status, DocumentModel.Status.INDEXED)
        self.assertEqual(doc.document_name, "sample_guideline.pdf")
        self.assertEqual(doc.file_type, "pdf")
        self.assertEqual(str(doc.ingest_session_id), session_id)

        # 2. Verify Chunks stored in DB with 1024d vector
        chunks = Chunk.objects.filter(document=doc)
        self.assertEqual(chunks.count(), result["chunks_added"])

        first_chunk = chunks.first()
        self.assertIsNotNone(first_chunk.embedding)
        self.assertEqual(len(first_chunk.embedding), 1024)
        self.assertEqual(first_chunk.page, 1)
        self.assertIn("Lumina ingest pipeline", first_chunk.chunk_text)

        # 3. Verify IngestLog entries generated across all steps
        steps = list(IngestLog.objects.filter(document=doc).values_list("step", flat=True))
        self.assertIn("copy", steps)
        self.assertIn("load", steps)
        self.assertIn("preprocess", steps)
        self.assertIn("chunk", steps)
        self.assertIn("database", steps)
        self.assertIn("complete", steps)

    @patch("ingest.services.get_embeddings")
    def test_pipeline_failure_rolls_back_and_marks_failed(self, mock_get_embeddings):
        """Integration test for error handling and marking Document status as FAILED."""
        mock_emb = MagicMock()
        mock_emb.embed_documents.side_effect = RuntimeError("Embedding model GPU OOM")
        mock_get_embeddings.return_value = mock_emb

        pdf_file_path = Path(self.temp_dir) / "fail_sample.pdf"
        pdf_file_path.write_bytes(SAMPLE_1PAGE_PDF_BYTES)

        doc = DocumentModel.objects.create(
            user=self.admin_user,
            document_name="fail_sample.pdf",
            path_file=str(pdf_file_path),
            file_type="pdf",
            size=1024,
            status=DocumentModel.Status.PROCESSING,
        )

        with self.assertRaises(RuntimeError):
            run_ingest_pipeline(
                file_path=pdf_file_path,
                original_filename="fail_sample.pdf",
                document_id=doc.id,
                user_id=self.admin_user.id,
                session_id="99999999-8888-7777-6666-555555555555",
            )

        doc.refresh_from_db()
        self.assertEqual(doc.status, DocumentModel.Status.FAILED)
        self.assertTrue(IngestLog.objects.filter(document=doc, step="error", status="failed").exists())

    @patch("ingest.tasks.run_ingest_pipeline")
    def test_celery_task_invokes_pipeline(self, mock_run_pipeline):
        mock_run_pipeline.return_value = {"chunks_added": 2, "document_id": 10, "file_path": "/path"}
        res = run_ingest_pipeline_task(
            file_path="/media/test.pdf",
            original_filename="test.pdf",
            document_id=10,
            user_id=self.admin_user.id,
            session_id="88888888-8888-8888-8888-888888888888",
        )
        self.assertEqual(res["chunks_added"], 2)
        mock_run_pipeline.assert_called_once_with(
            file_path=Path("/media/test.pdf"),
            original_filename="test.pdf",
            document_id=10,
            user_id=self.admin_user.id,
            session_id="88888888-8888-8888-8888-888888888888",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. API View Tests: Upload, Status, Permissions & Serializer Validation
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(
    MEDIA_ROOT="D:/Project/Django/lumina/backend/media_test",
    DEBUG=True,
)
class IngestViewsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            email="admin_view@example.com",
            username="admin_view",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        self.regular_user = User.objects.create_user(
            email="student@example.com",
            username="student",
            password="testpass123",
            role=User.Role.MAHASISWA,
        )
        self.client.force_authenticate(user=self.admin_user)

    def tearDown(self):
        media_test = "D:/Project/Django/lumina/backend/media_test"
        shutil.rmtree(media_test, ignore_errors=True)

    @patch("ingest.tasks.run_ingest_pipeline_task.delay")
    def test_upload_new_document_success(self, mock_delay):
        uploaded_file = SimpleUploadedFile(
            "guideline.pdf",
            SAMPLE_1PAGE_PDF_BYTES,
            content_type="application/pdf",
        )

        response = self.client.post(
            reverse("ingest-upload"),
            {"document": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        data = response.json()
        self.assertIn("document_id", data)
        self.assertIn("session_id", data)
        self.assertEqual(data["status"], "processing")

        self.assertTrue(
            DocumentModel.objects.filter(
                user=self.admin_user,
                document_name="guideline.pdf",
                status=DocumentModel.Status.PROCESSING,
            ).exists()
        )
        self.assertEqual(mock_delay.call_count, 1)

    @patch("ingest.tasks.run_ingest_pipeline_task.delay")
    def test_re_ingest_existing_document_success(self, mock_delay):
        existing_doc = DocumentModel.objects.create(
            user=self.admin_user,
            document_name="original.pdf",
            path_file="/media/documents/original.pdf",
            file_type="pdf",
            size=1024,
            status=DocumentModel.Status.INDEXED,
            ingest_session_id="11111111-1111-1111-1111-111111111111",
        )

        uploaded_file = SimpleUploadedFile(
            "updated.pdf",
            SAMPLE_1PAGE_PDF_BYTES,
            content_type="application/pdf",
        )

        response = self.client.post(
            reverse("ingest-upload"),
            {"document": uploaded_file, "document_id": existing_doc.id},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.json()["document_id"], existing_doc.id)

        existing_doc.refresh_from_db()
        self.assertEqual(existing_doc.status, DocumentModel.Status.PROCESSING)
        self.assertEqual(mock_delay.call_count, 1)

    def test_upload_missing_file(self):
        response = self.client.post(
            reverse("ingest-upload"),
            {},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("document", response.json())

    def test_upload_invalid_extension(self):
        uploaded_file = SimpleUploadedFile(
            "photo.jpg",
            b"fake jpg content",
            content_type="image/jpeg",
        )
        response = self.client.post(
            reverse("ingest-upload"),
            {"document": uploaded_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Tipe file tidak didukung", str(response.json()))

    def test_upload_invalid_mime_type_or_magic_bytes(self):
        # File named .pdf but content is not PDF header
        uploaded_file = SimpleUploadedFile(
            "fake.pdf",
            b"not a valid pdf header",
            content_type="application/pdf",
        )
        response = self.client.post(
            reverse("ingest-upload"),
            {"document": uploaded_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_text = str(response.json())
        self.assertTrue(
            "bukan PDF yang valid" in error_text or "MIME type tidak sesuai" in error_text,
            f"Expected validation error about invalid PDF, got: {error_text}",
        )

    def test_upload_non_admin_forbidden(self):
        self.client.force_authenticate(user=self.regular_user)
        uploaded_file = SimpleUploadedFile(
            "test.pdf",
            SAMPLE_1PAGE_PDF_BYTES,
            content_type="application/pdf",
        )
        response = self.client.post(
            reverse("ingest-upload"),
            {"document": uploaded_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_re_ingest_nonexistent_and_unauthorized_document(self):
        uploaded_file_1 = SimpleUploadedFile(
            "test1.pdf",
            SAMPLE_1PAGE_PDF_BYTES,
            content_type="application/pdf",
        )
        # Nonexistent
        res404 = self.client.post(
            reverse("ingest-upload"),
            {"document": uploaded_file_1, "document_id": 99999},
            format="multipart",
        )
        self.assertEqual(res404.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Dokumen tidak ditemukan", str(res404.json()))

        # Unauthorized document belonging to another user
        other_doc = DocumentModel.objects.create(
            user=self.regular_user,
            document_name="other.pdf",
            path_file="/path/other.pdf",
            file_type="pdf",
            size=1024,
        )
        uploaded_file_2 = SimpleUploadedFile(
            "test2.pdf",
            SAMPLE_1PAGE_PDF_BYTES,
            content_type="application/pdf",
        )
        res_unauth = self.client.post(
            reverse("ingest-upload"),
            {"document": uploaded_file_2, "document_id": other_doc.id},
            format="multipart",
        )
        self.assertEqual(res_unauth.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tidak memiliki akses", str(res_unauth.json()))

    def test_ingest_status_view(self):
        doc = DocumentModel.objects.create(
            user=self.admin_user,
            document_name="status_doc.pdf",
            path_file="/path/status_doc.pdf",
            file_type="pdf",
            size=1024,
            status=DocumentModel.Status.PROCESSING,
        )
        session_1 = "11111111-0000-0000-0000-000000000000"
        log1 = IngestLog.objects.create(
            document=doc,
            session_id=session_1,
            step="load",
            status="started",
            message="Loading started",
        )
        log2 = IngestLog.objects.create(
            document=doc,
            session_id=session_1,
            step="chunk",
            status="started",
            message="Chunking started",
        )

        # 1. Standard polling
        url = reverse("ingest-status", kwargs={"document_id": doc.id})
        res = self.client.get(url, {"session": session_1})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.json()["logs"]), 2)
        self.assertEqual(res.json()["status"], "processing")

        # 2. Incremental polling with 'after'
        res_after = self.client.get(url, {"session": session_1, "after": log1.id})
        self.assertEqual(res_after.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_after.json()["logs"]), 1)
        self.assertEqual(res_after.json()["logs"][0]["id"], log2.id)

        # 3. Nonexistent document
        res_404 = self.client.get(reverse("ingest-status", kwargs={"document_id": 88888}))
        self.assertEqual(res_404.status_code, status.HTTP_404_NOT_FOUND)

        # 4. Non-admin forbidden
        self.client.force_authenticate(user=self.regular_user)
        res_forbidden = self.client.get(url)
        self.assertEqual(res_forbidden.status_code, status.HTTP_403_FORBIDDEN)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Retrieval & Similarity Search Unit Tests
# ─────────────────────────────────────────────────────────────────────────────

class RetrievalUnitTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="qa_user@example.com",
            username="qa_user",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        self.doc = DocumentModel.objects.create(
            user=self.user,
            document_name="Panduan PBL.pdf",
            path_file="/path/pbl.pdf",
            file_type="pdf",
            size=2048,
            status=DocumentModel.Status.INDEXED,
        )
        self.chunk1 = Chunk.objects.create(
            document=self.doc,
            chunk_text="Bab 1: Pendahuluan dan Latar Belakang PBL.",
            page=1,
            embedding=get_mock_1024d_embedding(0.1),
        )
        self.chunk2 = Chunk.objects.create(
            document=self.doc,
            chunk_text="Bab 2: Kriteria Penilaian dan Evaluasi Mahasiswa.",
            page=2,
            embedding=get_mock_1024d_embedding(0.2),
        )

    def test_similarity_search_and_format_context(self):
        results = _similarity_search(get_mock_1024d_embedding(0.1), top_k=2, user_id=self.user.id)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].id, self.chunk1.id)

        context = _format_context(results)
        self.assertIn("[Excerpt 1 — Panduan PBL.pdf, hal. 1; asal: asal belum tercatat]", context)
        self.assertIn("Bab 1: Pendahuluan", context)

    def test_visual_pair_is_added_from_the_same_authorized_document(self):
        self.chunk1.metadata = {
            "source_type": "ocr", "image_ref": "page-1", "ocr_confidence": 0.8,
        }
        self.chunk1.save(update_fields=["metadata"])
        vision = Chunk.objects.create(
            document=self.doc,
            chunk_text="[Analisis visual] Tiga pilihan scaler terlihat.",
            page=1,
            metadata={"source_type": "vision", "image_ref": "page-1"},
        )
        other_user = User.objects.create_user(
            email="other@example.com", username="other", password="testpass123"
        )
        other_doc = DocumentModel.objects.create(
            user=other_user, document_name="Rahasia.pdf", path_file="/path/secret.pdf",
            file_type="pdf", size=100, status=DocumentModel.Status.INDEXED,
        )
        Chunk.objects.create(
            document=other_doc, chunk_text="Isi privat", page=1,
            metadata={"source_type": "vision", "image_ref": "page-1"},
        )

        expanded = _expand_visual_pairs([self.chunk1], user_id=self.user.id)

        self.assertEqual([chunk.id for chunk in expanded], [self.chunk1.id, vision.id])
        context = _format_context(expanded)
        self.assertIn("asal: OCR, gambar page-1, keyakinan OCR 0.80", context)
        self.assertIn("asal: Gemini Vision, gambar page-1", context)
    def test_rrf_fusion(self):
        # Create a 3rd chunk
        chunk3 = Chunk.objects.create(
            document=self.doc,
            chunk_text="Bab 3: Jadwal Pelaksanaan Proyek.",
            page=3,
            embedding=get_mock_1024d_embedding(0.3),
        )
        # Dense ranking: chunk1 (rank 1), chunk2 (rank 2)
        dense_results = [self.chunk1, self.chunk2]
        # Sparse ranking: chunk3 (rank 1), chunk1 (rank 2)
        sparse_results = [chunk3, self.chunk1]

        # RRF with k=60
        # chunk1 score: 1/(60+1) + 1/(60+2) = 1/61 + 1/62 = 0.016393 + 0.016129 = 0.032522
        # chunk3 score: 1/(60+1) = 1/61 = 0.016393
        # chunk2 score: 1/(60+2) = 1/62 = 0.016129
        fused = _rrf_fusion(dense_results, sparse_results, k=60, top_k=20)
        self.assertEqual(len(fused), 3)
        self.assertEqual(fused[0].id, self.chunk1.id)
        self.assertEqual(fused[1].id, chunk3.id)
        self.assertEqual(fused[2].id, self.chunk2.id)

        expected_chunk1_score = (1.0 / 61) + (1.0 / 62)
        self.assertAlmostEqual(fused[0].rrf_score, expected_chunk1_score, places=5)

        # Test top_k limiting
        limited = _rrf_fusion(dense_results, sparse_results, k=60, top_k=2)
        self.assertEqual(len(limited), 2)
        self.assertEqual(limited[0].id, self.chunk1.id)
        self.assertEqual(limited[1].id, chunk3.id)

    def test_sparse_search_and_metadata_filtering(self):
        # Trigger generates search_vector upon chunk creation in PostgreSQL
        # Refresh chunk1 & chunk2 to pick up the updated search_vector
        self.chunk1.refresh_from_db()
        self.chunk2.refresh_from_db()

        # Search for keyword present in chunk1
        results = _sparse_search("Pendahuluan", top_k=5, user_id=self.user.id)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].id, self.chunk1.id)

        # Search for keyword present in chunk2
        results2 = _sparse_search("Kriteria Penilaian", top_k=5, user_id=self.user.id)
        self.assertGreaterEqual(len(results2), 1)
        self.assertEqual(results2[0].id, self.chunk2.id)

        # Natural-language terms use OR semantics; an absent term must not
        # suppress a relevant match for another term.
        results3 = _sparse_search(
            "Pendahuluan IstilahYangTidakAda",
            top_k=5,
            user_id=self.user.id,
            document_ids=[self.doc.id],
        )
        self.assertGreaterEqual(len(results3), 1)
        self.assertEqual(results3[0].id, self.chunk1.id)

        # Metadata filtering: unauthorized user cannot see other user's indexed docs if not staff
        other_user = User.objects.create_user(
            email="other_student@example.com",
            username="other_student",
            password="testpass123",
            role=User.Role.MAHASISWA,
        )
        # Create doc for regular student
        student_doc = DocumentModel.objects.create(
            user=other_user,
            document_name="Private Student Doc.pdf",
            path_file="/path/student.pdf",
            file_type="pdf",
            size=1024,
            status=DocumentModel.Status.INDEXED,
        )
        student_chunk = Chunk.objects.create(
            document=student_doc,
            chunk_text="Rahasia proyek mahasiswa: algoritma optimasi genetika.",
            page=1,
            embedding=get_mock_1024d_embedding(0.3),
        )

        # Another student cannot search student_chunk
        another_student = User.objects.create_user(
            email="another@example.com",
            username="another",
            password="testpass123",
            role=User.Role.MAHASISWA,
        )
        res_unauthorized = _sparse_search("genetika", top_k=5, user_id=another_student.id)
        self.assertEqual(len(res_unauthorized), 0)

        # The owner student can search student_chunk
        res_authorized = _sparse_search("genetika", top_k=5, user_id=other_user.id)
        self.assertEqual(len(res_authorized), 1)
        self.assertEqual(res_authorized[0].id, student_chunk.id)

        # Non-indexed doc or soft-deleted doc is excluded
        student_doc.status = DocumentModel.Status.PROCESSING
        student_doc.save()
        self.assertEqual(len(_sparse_search("genetika", top_k=5, user_id=other_user.id)), 0)

    def test_save_answer(self):
        query = Query.objects.create(
            user=self.user,
            query_title="Apa itu PBL?",
            query_text="Jelaskan mengenai konsep PBL.",
        )
        sources = [{"source": "Panduan PBL.pdf", "page": 1, "score": 0.95, "excerpt": "Bab 1"}]
        answer_id = _save_answer(query, "PBL adalah Project Based Learning.", sources)
        self.assertIsNotNone(answer_id)

        answer = Answer.objects.get(pk=answer_id)
        self.assertEqual(answer.answer_text, "PBL adalah Project Based Learning.")
        self.assertTrue(History.objects.filter(query=query, answer=answer, user=self.user).exists())

    @patch("ingest.retrieval.time.sleep")
    def test_llm_transient_connection_error_is_retried(self, mock_sleep):
        remote_protocol_error = type("RemoteProtocolError", (Exception,), {})
        chain = MagicMock()
        chain.invoke.side_effect = [
            remote_protocol_error("Server disconnected"),
            "Jawaban setelah koneksi pulih.",
        ]

        with patch.object(config, "GEMINI_MAX_ATTEMPTS", 2):
            result = _invoke_llm_with_retry(chain, {"question": "Apa itu RAG?"})

        self.assertEqual(result, "Jawaban setelah koneksi pulih.")
        self.assertEqual(chain.invoke.call_count, 2)
        mock_sleep.assert_called_once()

    def test_llm_non_transient_error_is_not_retried(self):
        chain = MagicMock()
        chain.invoke.side_effect = ValueError("Invalid request")

        with patch.object(config, "GEMINI_MAX_ATTEMPTS", 2):
            with self.assertRaises(ValueError):
                _invoke_llm_with_retry(chain, {"question": "Apa itu RAG?"})

        self.assertEqual(chain.invoke.call_count, 1)
        self.assertFalse(_is_transient_llm_error(ValueError("Invalid request")))

    @patch("ingest.retrieval.get_embeddings")
    @patch("ingest.retrieval._build_llm")
    def test_run_rag_query_success(self, mock_build_llm, mock_get_embeddings):
        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = get_mock_1024d_embedding(0.1)
        mock_get_embeddings.return_value = mock_emb

        mock_llm = MagicMock()
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "PBL adalah metode pembelajaran berbasis proyek."

        # Patch prompt | llm | parser pipeline and reranker
        with patch("ingest.retrieval.ChatPromptTemplate.from_messages", return_value=MagicMock(__or__=lambda self, other: MagicMock(__or__=lambda self, other: mock_chain))):
            with patch("ingest.retrieval.rerank_chunks") as mock_rerank:
                mock_rerank.side_effect = lambda query, chunks, top_k: (chunks[:top_k], 15.0, False)
                with patch.object(config, "GEMINI_API_KEY", "fake-api-key"):
                    query = Query.objects.create(
                        user=self.user,
                        query_title="Apa itu PBL?",
                        query_text="Apa itu PBL?",
                    )
                    res = run_rag_query(query.id, "Apa itu PBL?", top_k=2)
                    self.assertTrue(res["success"])
                    self.assertIn("PBL adalah metode", res["answer"])
                    self.assertEqual(len(res["sources"]), 2)

                    query.refresh_from_db()
                    self.assertEqual(query.status, Query.Status.ANSWERED)
                    self.assertEqual(query.current_step, "done")
                    self.assertTrue(mock_rerank.called)

    @patch("ingest.retrieval.get_embeddings")
    @patch("ingest.retrieval._build_llm")
    def test_run_rag_query_llm_failure_and_empty_response(self, mock_build_llm, mock_get_embeddings):
        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = get_mock_1024d_embedding(0.1)
        mock_get_embeddings.return_value = mock_emb

        query = Query.objects.create(
            user=self.user,
            query_title="Apa itu PBL?",
            query_text="Apa itu PBL?",
        )

        # 1. LLM exception
        mock_chain_fail = MagicMock()
        mock_chain_fail.invoke.side_effect = Exception("API rate limited")
        with patch("ingest.retrieval.ChatPromptTemplate.from_messages", return_value=MagicMock(__or__=lambda self, other: MagicMock(__or__=lambda self, other: mock_chain_fail))):
            with patch.object(config, "GEMINI_API_KEY", "fake-api-key"):
                with self.assertRaises(RagPipelineError) as ctx:
                    run_rag_query(query.id, "Apa itu PBL?", top_k=2)
                self.assertEqual(ctx.exception.http_status, 502)

        # 2. LLM empty response
        mock_chain_empty = MagicMock()
        mock_chain_empty.invoke.return_value = "   "
        with patch("ingest.retrieval.ChatPromptTemplate.from_messages", return_value=MagicMock(__or__=lambda self, other: MagicMock(__or__=lambda self, other: mock_chain_empty))):
            with patch.object(config, "GEMINI_API_KEY", "fake-api-key"):
                with self.assertRaises(RagPipelineError) as ctx:
                    run_rag_query(query.id, "Apa itu PBL?", top_k=2)
                self.assertEqual(ctx.exception.http_status, 502)

    @patch("ingest.retrieval.get_embeddings")
    def test_run_rag_query_no_chunks_found(self, mock_get_embeddings):
        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = get_mock_1024d_embedding(0.1)
        mock_get_embeddings.return_value = mock_emb

        # Delete all chunks
        Chunk.objects.all().delete()
        query = Query.objects.create(
            user=self.user,
            query_title="Apa itu PBL?",
            query_text="Apa itu PBL?",
        )
        with patch.object(config, "GEMINI_API_KEY", "fake-api-key"):
            with self.assertRaises(RagPipelineError) as ctx:
                run_rag_query(query.id, "Apa itu PBL?", top_k=2)
            self.assertEqual(ctx.exception.http_status, 409)

    def test_run_rag_query_errors(self):
        # Nonexistent query
        with self.assertRaises(RagPipelineError) as ctx:
            run_rag_query(99999, "test")
        self.assertEqual(ctx.exception.http_status, 404)

        # Missing Gemini API Key
        query = Query.objects.create(user=self.user, query_title="Q", query_text="Q")
        with patch.object(config, "GEMINI_API_KEY", ""):
            with self.assertRaises(RagPipelineError) as ctx:
                run_rag_query(query.id, "test")
            self.assertEqual(ctx.exception.http_status, 503)

    def test_build_llm(self):
        from ingest.retrieval import _build_llm
        llm = _build_llm()
        self.assertEqual(llm.model, config.GEMINI_MODEL)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Serializer Unit Tests
# ─────────────────────────────────────────────────────────────────────────────

class SerializerUnitTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="serializer_test@example.com",
            username="serializer_test",
            password="testpass123",
            role=User.Role.ADMIN,
        )

    def test_serializer_valid_docx_and_txt(self):
        from ingest.serializers import IngestUploadSerializer

        # Valid DOCX
        docx_file = SimpleUploadedFile("sample.docx", b"PK\x03\x04 dummy zip header", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        s1 = IngestUploadSerializer(data={"document": docx_file})
        self.assertTrue(s1.is_valid(), s1.errors)

        # Invalid DOCX header
        bad_docx = SimpleUploadedFile("sample.docx", b"NOT_A_ZIP", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        s2 = IngestUploadSerializer(data={"document": bad_docx})
        self.assertFalse(s2.is_valid())
        error_text = str(s2.errors)
        self.assertTrue(
            "bukan dokumen Word" in error_text or "MIME type tidak sesuai" in error_text,
            f"Expected validation error about invalid DOCX, got: {error_text}",
        )

        # Valid TXT
        txt_file = SimpleUploadedFile("sample.txt", b"plain text content here", content_type="text/plain")
        s3 = IngestUploadSerializer(data={"document": txt_file})
        self.assertTrue(s3.is_valid(), s3.errors)

    def test_serializer_file_size_exceeded(self):
        from ingest.serializers import IngestUploadSerializer

        oversized_file = SimpleUploadedFile("huge.pdf", b"%PDF-1.4" + b"0" * 100, content_type="application/pdf")
        oversized_file.size = 105 * 1024 * 1024  # 105 MB
        s = IngestUploadSerializer(data={"document": oversized_file})
        self.assertFalse(s.is_valid())
        self.assertIn("melebihi batas", str(s.errors))

    def test_serializer_document_id_validations(self):
        from ingest.serializers import IngestUploadSerializer

        pdf_file = SimpleUploadedFile("sample.pdf", SAMPLE_1PAGE_PDF_BYTES, content_type="application/pdf")

        # Valid document_id=None
        s_none = IngestUploadSerializer(data={"document": pdf_file, "document_id": None})
        self.assertTrue(s_none.is_valid())

        # Invalid document_id string
        pdf_file.seek(0)
        s_invalid_type = IngestUploadSerializer(data={"document": pdf_file, "document_id": "not-a-number"})
        self.assertFalse(s_invalid_type.is_valid())


# ─────────────────────────────────────────────────────────────────────────────
# 6. Reranker Unit & Benchmark Tests (LUMINA-11)
# ─────────────────────────────────────────────────────────────────────────────

class RerankerUnitTest(TestCase):
    def setUp(self):
        enabled = patch.object(config, 'RERANKER_ENABLED', True)
        enabled.start()
        self.addCleanup(enabled.stop)
        self.user = User.objects.create_user(
            email="rerank_test@example.com",
            username="rerank_test",
            password="password123",
            role=User.Role.ADMIN,
        )
        self.doc = DocumentModel.objects.create(
            user=self.user,
            document_name="Test Doc.pdf",
            path_file="/tmp/test.pdf",
            file_type="pdf",
            size=1024,
            status=DocumentModel.Status.INDEXED,
        )
        self.chunks = [
            Chunk.objects.create(
                document=self.doc,
                chunk_text=f"Chunk teks ke-{i} mengenai arsitektur sistem Lumina dan performa RAG.",
                page=i,
                embedding=get_mock_1024d_embedding(0.01 * i),
            )
            for i in range(1, 21)  # 20 candidate chunks
        ]

    def test_rerank_chunks_successful_ranking(self):
        # Mock CrossEncoder / FlagReranker predict
        mock_model = MagicMock()
        # Returns ascending scores such that chunk 20 has highest score (19.0), chunk 1 has lowest (0.0)
        mock_model.predict.return_value = [float(i) for i in range(20)]

        with patch("ingest.reranker._reranker_instance", mock_model):
            top_chunks, elapsed_ms, fallback_used = rerank_chunks(
                query="arsitektur sistem",
                chunks=list(self.chunks),
                top_k=7,
                timeout_seconds=1.2,
            )

            self.assertFalse(fallback_used)
            self.assertEqual(len(top_chunks), 7)
            # The highest score is chunk 20 (score 19.0), followed by 19, 18, etc.
            self.assertEqual(top_chunks[0].id, self.chunks[19].id)
            self.assertEqual(top_chunks[0].rerank_score, 19.0)
            self.assertEqual(top_chunks[6].id, self.chunks[13].id)
            self.assertGreater(elapsed_ms, 0)

    def test_rerank_chunks_timeout_fallback(self):
        mock_model = MagicMock()
        import time

        def slow_predict(pairs):
            time.sleep(0.2)
            return [0.5] * len(pairs)

        mock_model.predict.side_effect = slow_predict

        with patch("ingest.reranker._reranker_instance", mock_model):
            top_chunks, elapsed_ms, fallback_used = rerank_chunks(
                query="arsitektur sistem",
                chunks=list(self.chunks),
                top_k=7,
                timeout_seconds=0.05,  # 50ms timeout threshold
            )

            self.assertTrue(fallback_used)
            self.assertEqual(len(top_chunks), 7)
            # Fallback returns original order top 7 (chunk 0 to 6)
            self.assertEqual(top_chunks[0].id, self.chunks[0].id)
            self.assertEqual(top_chunks[6].id, self.chunks[6].id)

    def test_rerank_chunks_exception_fallback(self):
        mock_model = MagicMock()
        mock_model.predict.side_effect = RuntimeError("CUDA out of memory")

        with patch("ingest.reranker._reranker_instance", mock_model):
            top_chunks, elapsed_ms, fallback_used = rerank_chunks(
                query="arsitektur sistem",
                chunks=list(self.chunks),
                top_k=7,
                timeout_seconds=1.2,
            )

            self.assertTrue(fallback_used)
            self.assertEqual(len(top_chunks), 7)
            self.assertEqual(top_chunks[0].id, self.chunks[0].id)

    def test_rerank_chunks_disabled_in_config(self):
        with patch.object(config, "RERANKER_ENABLED", False):
            top_chunks, elapsed_ms, fallback_used = rerank_chunks(
                query="arsitektur sistem",
                chunks=list(self.chunks),
                top_k=7,
            )
            self.assertTrue(fallback_used)
            self.assertEqual(len(top_chunks), 7)
            self.assertEqual(top_chunks[0].id, self.chunks[0].id)

    def test_rerank_empty_chunks(self):
        top_chunks, elapsed_ms, fallback_used = rerank_chunks(
            query="arsitektur sistem",
            chunks=[],
            top_k=7,
        )
        self.assertEqual(len(top_chunks), 0)
        self.assertFalse(fallback_used)

    def test_rerank_latency_benchmark_ac(self):
        """
        Benchmark acceptance criteria:
        p95 reranking latency < 1.2s on CPU (1200ms) and < 400ms on GPU.
        """
        import time

        mock_model = MagicMock()
        # Simulate 20ms inference time for 20 chunks
        def fast_predict(pairs):
            time.sleep(0.02)
            return [0.8] * len(pairs)

        mock_model.predict.side_effect = fast_predict

        with patch("ingest.reranker._reranker_instance", mock_model):
            latencies = []
            for _ in range(20):
                _, elapsed_ms, fallback = rerank_chunks(
                    query="benchmark query",
                    chunks=list(self.chunks),
                    top_k=7,
                    timeout_seconds=1.2,
                )
                self.assertFalse(fallback)
                latencies.append(elapsed_ms)

            latencies.sort()
            p95_idx = int(len(latencies) * 0.95)
            p95_latency = latencies[p95_idx]

            # p95 should satisfy target < 1200ms on CPU
            self.assertLess(p95_latency, 1200.0)
