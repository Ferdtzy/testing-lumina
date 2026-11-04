import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from .retrieval_ablation import _result_rows, faiss_dense_search, read_brief_questions


class RetrievalAblationTests(unittest.TestCase):
    def test_reads_brief_csv_and_rejects_duplicate_qid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "questions.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=["qid", "gold_doc", "question", "gold_pages", "reference", "qtype"],
                )
                writer.writeheader()
                writer.writerow({"qid": "Q001", "question": "Pertanyaan pertama?"})
                writer.writerow({"qid": "Q001", "question": "Pertanyaan kedua?"})
            with self.assertRaisesRegex(ValueError, "duplikat"):
                read_brief_questions(path, require_100=False)

    def test_reads_semicolon_csv_with_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "questions.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    delimiter=";",
                    fieldnames=["qid", "gold_doc", "question", "gold_pages", "reference", "qtype"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "qid": "Q001",
                        "gold_doc": "Dokumen.pdf",
                        "question": "Apa isi dokumen?",
                        "gold_pages": "2;3",
                        "reference": "Isi acuan",
                        "qtype": "multi",
                    }
                )

            rows = read_brief_questions(path, require_100=False)

            self.assertEqual(rows[0]["qid"], "Q001")
            self.assertEqual(rows[0]["gold_pages"], "2;3")

    def test_dense_score_is_cosine_similarity_and_page_is_not_incremented(self):
        chunk = SimpleNamespace(
            distance=0.125,
            page=4,
            document=SimpleNamespace(document_name="Kurikulum-IF.pdf"),
        )
        row = _result_rows("dense", [chunk], 10)[0]
        self.assertEqual(row["score"], "0.875000")
        self.assertEqual(row["page"], 4)

    def test_native_scores_are_preserved_per_configuration(self):
        document = SimpleNamespace(document_name="Dokumen.pdf")
        text = SimpleNamespace(rank=0.42, page=1, document=document)
        rrf = SimpleNamespace(rrf_score=0.0328, page=1, document=document)
        lumina = SimpleNamespace(rerank_score=0.9917, page=1, document=document)
        self.assertEqual(_result_rows("text", [text], 10)[0]["score"], "0.420000")
        self.assertEqual(_result_rows("rrf", [rrf], 10)[0]["score"], "0.032800")
        self.assertEqual(_result_rows("lumina", [lumina], 10)[0]["score"], "0.991700")

    def test_faiss_dense_search_uses_cosine_similarity(self):
        try:
            import faiss
            import numpy as np
        except ImportError:
            self.skipTest("faiss-cpu belum terpasang")

        vectors = np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype="float32")
        index = faiss.IndexFlatIP(2)
        index.add(vectors)
        chunks = [SimpleNamespace(), SimpleNamespace()]

        results = faiss_dense_search(index, chunks, [0.9, 0.1], 2)

        self.assertIs(results[0], chunks[0])
        self.assertGreater(1.0 - results[0].distance, 1.0 - results[1].distance)


if __name__ == "__main__":
    unittest.main()
