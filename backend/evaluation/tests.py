from django.test import SimpleTestCase

from .management.commands.evaluate_rag import contains_all_terms


class GoldenCaseTermTests(SimpleTestCase):
    def test_all_expected_terms_are_required_case_insensitively(self):
        self.assertTrue(contains_all_terms("Standard, Minmax dan Robust", ["standard", "MINMAX", "robust"]))
        self.assertFalse(contains_all_terms("Standard dan Minmax", ["standard", "minmax", "robust"]))
