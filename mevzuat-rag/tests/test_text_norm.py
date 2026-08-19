"""Unit tests for mevzuat_rag.text_norm.

All cases are pure functions; no model, network, or storage required.
"""
from __future__ import annotations

import unicodedata
import unittest

from mevzuat_rag.text_norm import normalize_text


class NormalizeTextGeneralTests(unittest.TestCase):
    def test_nfc_normalization_composes_decomposed_input(self):
        decomposed = unicodedata.normalize("NFD", "İü")
        self.assertEqual(normalize_text(decomposed, profile="embedding"), "İü")

    def test_whitespace_normalization(self):
        self.assertEqual(normalize_text("  a   b\tc  ", profile="embedding"), "a b c")
        self.assertEqual(normalize_text("a\r\nb\rc", profile="embedding"), "a\nb\nc")
        self.assertEqual(normalize_text("a\n\n\nb", profile="embedding"), "a\n\nb")

    def test_dehyphenation_joins_line_break_hyphen(self):
        self.assertEqual(normalize_text("kanun-\nun", profile="embedding"), "kanunun")

    def test_invisible_characters_are_removed_or_normalized(self):
        text = "a​b­c d"
        self.assertEqual(normalize_text(text, profile="embedding"), "abc d")

    def test_curly_quotes_are_normalized_to_ascii(self):
        text = "“merhaba” ‘dünya’"
        self.assertEqual(normalize_text(text, profile="embedding"), "\"merhaba\" 'dünya'")

    def test_negative_cases_are_not_touched(self):
        self.assertEqual(normalize_text("MADDE 5-", profile="embedding"), "MADDE 5-")
        self.assertEqual(normalize_text("01.01.2026", profile="embedding"), "01.01.2026")
        self.assertEqual(normalize_text("%50", profile="embedding"), "%50")
        self.assertEqual(
            normalize_text("3071 sayılı Kanun'un", profile="embedding"),
            "3071 sayılı Kanun'un",
        )

    def test_unknown_profile_raises_value_error(self):
        with self.assertRaises(ValueError):
            normalize_text("deneme", profile="bilinmeyen")

    def test_normalization_is_deterministic(self):
        text = "İstanbul'da   kanun-\nun “deneme”\r\nmetni"
        self.assertEqual(
            normalize_text(text, profile="embedding"),
            normalize_text(text, profile="embedding"),
        )
        self.assertEqual(
            normalize_text(text, profile="lexical"),
            normalize_text(text, profile="lexical"),
        )
        self.assertEqual(
            normalize_text(text, profile="display"),
            normalize_text(text, profile="display"),
        )


class NormalizeTextProfileTests(unittest.TestCase):
    def test_embedding_profile_preserves_turkish_case(self):
        self.assertEqual(normalize_text("İstanbul", profile="embedding"), "İstanbul")
        self.assertEqual(normalize_text("İSTANBUL", profile="embedding"), "İSTANBUL")

    def test_lexical_profile_turkish_lower_and_ascii_fold(self):
        self.assertEqual(normalize_text("İstanbul", profile="lexical"), "istanbul")
        self.assertEqual(normalize_text("İSTANBUL", profile="lexical"), "istanbul")
        self.assertEqual(normalize_text("Istanbul", profile="lexical"), "istanbul")
        self.assertEqual(normalize_text("I", profile="lexical"), "i")
        self.assertEqual(normalize_text("İ", profile="lexical"), "i")

    def test_embedding_and_lexical_profiles_differ(self):
        self.assertNotEqual(
            normalize_text("İSTANBUL", profile="embedding"),
            normalize_text("İSTANBUL", profile="lexical"),
        )

    def test_display_profile_cleans_whitespace_but_preserves_quotes_and_hyphenation(self):
        self.assertEqual(
            normalize_text("​kanun-\nun​", profile="display"),
            "kanun-\nun",
        )
        self.assertEqual(
            normalize_text("“merhaba”", profile="display"),
            "“merhaba”",
        )


if __name__ == "__main__":
    unittest.main()
