import unittest

from .chunk_token_audit import summarize_token_lengths


class ChunkTokenAuditTests(unittest.TestCase):
    def test_summarizes_lengths_and_uses_strict_over_threshold(self):
        result = summarize_token_lengths([100, 512, 513, 875])

        self.assertEqual(result["n_chunks"], 4)
        self.assertEqual(result["mean_tokens"], 500.0)
        self.assertEqual(result["median_tokens"], 512.5)
        self.assertEqual(result["max_tokens"], 875)
        self.assertEqual(result["pct_over_512"], 50.0)

    def test_rejects_empty_corpus(self):
        with self.assertRaisesRegex(ValueError, "tidak mempunyai chunk"):
            summarize_token_lengths([])


if __name__ == "__main__":
    unittest.main()
