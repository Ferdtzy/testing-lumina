from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from core.models import Chunk, Document


User = get_user_model()


class DocumentProcessingDetailApiTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="admin-summary@example.com",
            username="admin_summary",
            password="testpass123",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.client.force_authenticate(self.user)
        self.document = Document.objects.create(
            user=self.user,
            document_name="ringkasan.pdf",
            path_file="/tmp/ringkasan.pdf",
            file_type="pdf",
            size=1024,
            status=Document.Status.INDEXED,
        )
        Chunk.objects.create(
            document=self.document,
            chunk_text="Paragraf dokumen",
            page=1,
            metadata={"source_type": "document_text"},
        )
        Chunk.objects.create(
            document=self.document,
            chunk_text="Teks hasil OCR",
            page=1,
            metadata={
                "source_type": "ocr",
                "image_ref": "page-1-image-1",
                "ocr_confidence": 0.95,
            },
        )
        Chunk.objects.create(
            document=self.document,
            chunk_text="[Analisis visual] Diagram alur.",
            page=1,
            metadata={
                "source_type": "vision",
                "image_ref": "page-1-image-1",
            },
        )

    def test_document_list_contains_processing_summary(self):
        response = self.client.get("/api/documents/")

        self.assertEqual(response.status_code, 200)
        payload = response.data.get("results", response.data)
        item = next(row for row in payload if row["id"] == self.document.id)
        self.assertEqual(item["total_chunk_count"], 3)
        self.assertEqual(item["document_text_chunk_count"], 1)
        self.assertEqual(item["ocr_chunk_count"], 1)
        self.assertEqual(item["vision_chunk_count"], 1)
        self.assertEqual(item["processed_page_count"], 1)

    def test_chunk_detail_exposes_provenance_metadata(self):
        response = self.client.get(f"/api/documents/{self.document.id}/chunks/")

        self.assertEqual(response.status_code, 200)
        ocr_chunk = next(
            row for row in response.data if row["metadata"].get("source_type") == "ocr"
        )
        self.assertEqual(ocr_chunk["metadata"]["image_ref"], "page-1-image-1")
        self.assertEqual(ocr_chunk["metadata"]["ocr_confidence"], 0.95)
