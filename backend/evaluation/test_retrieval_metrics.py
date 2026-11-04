import unittest

from .retrieval_metrics import analyze_abstention, evaluate_answerable, parse_gold_pages, reciprocal_rank


class RetrievalMetricsTests(unittest.TestCase):
    def test_parse_gold_pages(self):
        self.assertEqual(parse_gold_pages("2; 3;5"), {2, 3, 5})
        self.assertEqual(parse_gold_pages(""), set())

    def test_reciprocal_rank(self):
        self.assertEqual(reciprocal_rank([False, True, True]), 0.5)
        self.assertEqual(reciprocal_rank([False] * 10), 0.0)

    def test_evaluates_document_and_page_metrics(self):
        question = {"gold_doc": "Gold.pdf", "gold_pages": "2;3"}
        results = [
            {"doc": "Other.pdf", "page": "2"},
            {"doc": "Gold.pdf", "page": "2"},
            {"doc": "Gold.pdf", "page": "8"},
            {"doc": "Gold.pdf", "page": "3"},
        ]

        metrics = evaluate_answerable(question, results)

        self.assertEqual(metrics["doc_recall_at_1"], 0.0)
        self.assertEqual(metrics["doc_recall_at_3"], 1.0)
        self.assertEqual(metrics["doc_mrr_at_10"], 0.5)
        self.assertEqual(metrics["page_hit_at_3"], 1.0)
        self.assertEqual(metrics["gold_page_recall_at_3"], 0.5)
        self.assertEqual(metrics["gold_page_recall_at_5"], 1.0)

    def test_analyzes_abstention_scores(self):
        result = analyze_abstention([(0.9, True), (0.8, True), (0.2, False), (0.1, False)])

        self.assertEqual(result["balanced_accuracy"], 1.0)
        self.assertEqual(result["answerable_accept_rate"], 1.0)
        self.assertEqual(result["unanswerable_reject_rate"], 1.0)
        self.assertEqual(result["auroc"], 1.0)


if __name__ == "__main__":
    unittest.main()
