"""Offline end-to-end metric checks; no requests to model providers."""
import unittest

from .runner import evaluate


class Embeddings:
    def embed_documents(self, texts):
        return [[1, 0] for _ in texts]

    def embed_query(self, text):
        return [1, 0]


class Judge:
    def extract(self, answer):
        return {'answer_status': 'substantive', 'claims': ['Normalisasi menyeragamkan data.', 'Akurasi dijamin 99%.']}

    def judge_claims(self, claims, contexts):
        return [{'claim': claims[0], 'verdict': 'supported', 'evidence': [{'chunk_id': 1, 'quote': 'Normalisasi menyeragamkan data.'}]},
                {'claim': claims[1], 'verdict': 'supported', 'evidence': [{'chunk_id': 1, 'quote': '99%'}]}]

    def reverse_questions(self, answer):
        return ['Apa fungsi normalisasi?', 'Mengapa normalisasi digunakan?', 'Apa tujuan normalisasi?']


class EvaluationFlowTest(unittest.TestCase):
    contexts = [{'chunk_id': 1, 'text': 'Normalisasi menyeragamkan data.'}]

    def test_unsupported_claim_reduces_faithfulness_and_blocks_release(self):
        result = evaluate('Apa fungsi normalisasi?', 'Normalisasi menyeragamkan data.', self.contexts,
                          'Normalisasi menyeragamkan data.', Judge(), Embeddings())
        self.assertEqual(result['metrics']['rouge_l'], 1)
        self.assertEqual(result['metrics']['semantic_similarity'], 1)
        self.assertEqual(result['metrics']['faithfulness'], .5)
        self.assertEqual(result['metrics']['answer_relevancy'], 1)
        self.assertFalse(result['groundedness_passed'])

    def test_absent_reference_leaves_reference_metrics_null(self):
        result = evaluate('Apa fungsi normalisasi?', 'Jawaban', self.contexts, '', Judge(), Embeddings())
        self.assertIsNone(result['metrics']['rouge_l'])
        self.assertIsNone(result['metrics']['semantic_similarity'])

    def test_pure_abstention_has_no_perfect_faithfulness(self):
        class Abstention(Judge):
            def extract(self, answer):
                return {'answer_status': 'abstention', 'claims': []}
        result = evaluate('Tanggal?', 'Tidak ditemukan.', self.contexts, '', Abstention(), Embeddings())
        self.assertIsNone(result['metrics']['faithfulness'])
        self.assertEqual(result['metrics']['answer_relevancy'], 0)
        self.assertFalse(result['groundedness_passed'])

    def test_wrong_claim_count_is_rejected_before_score(self):
        class Failed(Judge):
            def judge_claims(self, claims, contexts):
                raise ValueError('Missing verdicts')
        with self.assertLogs('evaluation.runner', level='ERROR'):
            result = evaluate('Pertanyaan', 'Jawaban', self.contexts, '', Failed(), Embeddings())
        self.assertIsNone(result['metrics']['faithfulness'])
        self.assertIn('faithfulness', result['evaluation_errors'])


if __name__ == '__main__':
    unittest.main()
