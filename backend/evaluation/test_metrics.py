import json
import tempfile
import unittest
from pathlib import Path

from .dataset import merge_references, read_questions, write_json
from .metrics import cosine, rouge_l, summarize, validate_claims


class EvaluationMetricsTest(unittest.TestCase):
    def test_unicode_and_case(self):
        self.assertEqual(rouge_l('Normalisasi DATA.', 'normalisasi data')['f1'], 1)

    def test_lcs_preserves_order(self):
        self.assertAlmostEqual(rouge_l('a b c', 'a c b')['f1'], 2/3)

    def test_empty_answer_and_unrelated_text(self):
        self.assertEqual(rouge_l('', 'acuan')['f1'], 0)
        self.assertEqual(rouge_l('satu', 'dua')['f1'], 0)

    def test_cosine_not_shifted_into_probability(self):
        self.assertEqual(cosine([1,0], [-1,0]), -1)
        self.assertEqual(cosine([1,0], [0,1]), 0)
        with self.assertRaises(ValueError):
            cosine([0,0], [1,0])

    def test_fake_evidence_is_not_supported(self):
        claims=[{'claim':'Akurasi 99%', 'verdict':'supported', 'evidence':[{'chunk_id':1,'quote':'99%'}]}]
        result=validate_claims(claims,[{'chunk_id':1,'text':'Normalisasi menyeragamkan data.'}])
        self.assertEqual(result[0]['verdict'], 'insufficient')

    def test_real_quote_and_newlines(self):
        claims=[{'claim':'Data dinormalisasi', 'verdict':'supported', 'evidence':[{'chunk_id':1,'quote':'normalisasi data'}]}]
        self.assertEqual(validate_claims(claims,[{'chunk_id':1,'text':'normalisasi\ndata'}])[0]['verdict'],'supported')

    def test_average_coverage_and_answer_rate(self):
        rows=[{'status':'evaluated','answer_status':'substantive','groundedness_passed':True,'metrics':{'rouge_l':1}},
              {'status':'error','answer_status':'error','metrics':{}}]
        summary=summarize(rows)
        self.assertEqual(summary['metrics']['rouge_l']['mean'],1)
        self.assertEqual(summary['metrics']['rouge_l']['missing_n'],1)
        self.assertEqual(summary['answer_rate']['value'],.5)

    def test_unknown_judgment_does_not_become_zero(self):
        summary=summarize([{'answer_status':'unknown','metrics':{},'evaluation_errors':['faithfulness']}])
        self.assertIsNone(summary['answer_rate']['value'])
        self.assertIsNone(summary['metrics']['faithfulness']['mean'])

    def test_failed_grounding_judge_does_not_imply_zero_grounded_rate(self):
        summary=summarize([{'answer_status':'substantive','groundedness_passed':None,'metrics':{}}])
        self.assertEqual(summary['answer_rate']['value'],1)
        self.assertIsNone(summary['grounded_answer_rate']['value'])

    def test_references_match_by_id_not_order(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            write_json(d/'q.json',{'questions':[{'id':1,'question':'A?'},{'id':2,'question':'B?'}]})
            write_json(d/'r.json',[{'id':2,'reference_answer':'B'},{'id':1,'reference_answer':'A'}])
            self.assertEqual(merge_references(d/'q.json',d/'r.json',d/'out.json'),2)
            self.assertEqual([r['reference_answer'] for r in read_questions(d/'out.json')],['A','B'])

    def test_duplicate_reference_ids_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            write_json(d/'q.json',[{'id':1,'question':'A?'}])
            write_json(d/'r.json',[{'id':1,'reference_answer':'A'},{'id':1,'reference_answer':'B'}])
            with self.assertRaises(ValueError):
                merge_references(d/'q.json',d/'r.json',d/'out.json')


if __name__ == '__main__':
    unittest.main()
