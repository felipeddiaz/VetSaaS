from django.test import SimpleTestCase

from apps.core.pdf_utils import safe_pdf_text, safe_filename_segment


class SafePdfTextTests(SimpleTestCase):
    def test_strips_nul_bytes(self):
        self.assertEqual(safe_pdf_text("hola\x00mundo"), "holamundo")

    def test_strips_other_control_chars(self):
        # \x07 = BEL, \x1f = US
        self.assertEqual(safe_pdf_text("a\x07b\x1fc"), "abc")

    def test_preserves_tab_newline_carriage_return(self):
        self.assertEqual(safe_pdf_text("a\tb\nc\rd"), "a\tb\nc\rd")

    def test_preserves_unicode(self):
        self.assertEqual(safe_pdf_text("Ñoño con tildes áéíóú"), "Ñoño con tildes áéíóú")

    def test_none_returns_default(self):
        self.assertEqual(safe_pdf_text(None), "")
        self.assertEqual(safe_pdf_text(None, default="-"), "-")

    def test_non_string_coerces(self):
        self.assertEqual(safe_pdf_text(42), "42")


class SafeFilenameSegmentTests(SimpleTestCase):
    def test_strips_punctuation(self):
        self.assertEqual(safe_filename_segment("Hola/mundo?.txt"), "Holamundotxt")

    def test_keeps_spaces_and_dashes(self):
        self.assertEqual(safe_filename_segment("Firulais-Garcia 2026"), "Firulais-Garcia 2026")

    def test_truncates(self):
        self.assertEqual(safe_filename_segment("a" * 100, max_length=10), "a" * 10)

    def test_empty(self):
        self.assertEqual(safe_filename_segment(""), "")
        self.assertEqual(safe_filename_segment(None), "")
