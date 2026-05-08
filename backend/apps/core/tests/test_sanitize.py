from django.test import SimpleTestCase
from apps.core.sanitize import sanitize_text


class SanitizeTextTest(SimpleTestCase):
    def test_xss_script_tag_removed(self):
        result = sanitize_text("<script>alert(1)</script>texto", max_length=5000)
        self.assertNotIn("<script>", result)
        self.assertIn("texto", result)

    def test_xss_img_onerror_removed(self):
        result = sanitize_text("<img src=x onerror=alert(1)>contenido", max_length=5000)
        self.assertNotIn("<img", result)
        self.assertIn("contenido", result)

    def test_max_length_truncates(self):
        result = sanitize_text("A" * 10_000, max_length=5000)
        self.assertEqual(len(result), 5000)

    def test_only_spaces_returns_empty(self):
        result = sanitize_text("     ", max_length=5000)
        self.assertEqual(result, "")

    def test_plain_text_preserved(self):
        result = sanitize_text("Diagnóstico normal sin HTML", max_length=5000)
        self.assertEqual(result, "Diagnóstico normal sin HTML")

    def test_none_returns_empty(self):
        result = sanitize_text(None, max_length=5000)
        self.assertEqual(result, "")
