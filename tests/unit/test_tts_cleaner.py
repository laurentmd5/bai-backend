"""
Unit tests for TTS text cleaning.
Tests emoji removal, keycap replacement, markdown stripping, and speech normalization.
"""

import pytest
from app.services.audio.tts_service import clean_text_for_tts


class TestTTSCleaner:
    """Tests for clean_text_for_tts."""

    def test_removes_emojis(self):
        """Emojis like checkmarks, pins, pages must be stripped for TTS."""
        input_text = "✅ Merci infiniment ! 📄 Votre CV a bien été reçu. 📌 Prochaines étapes."
        expected = "Merci infiniment ! Votre CV a bien été reçu. Prochaines étapes."
        assert clean_text_for_tts(input_text) == expected

    def test_converts_keycap_emojis(self):
        """Keycap emojis like 1️⃣, 2️⃣ must be converted to numbers."""
        input_text = "1️⃣ Avez-vous pris connaissance de l'offre ? 2️⃣ Êtes-vous disponible ?"
        expected = "1. Avez-vous pris connaissance de l'offre ? 2. Êtes-vous disponible ?"
        assert clean_text_for_tts(input_text) == expected

    def test_strips_markdown_formatting(self):
        """Markdown bold, italic, and code markers must be stripped."""
        input_text = "Chez *NETSYSTEME INFORMATIQUE*, pour un profil **Développeur** (`CV.pdf`)."
        expected = "Chez NETSYSTEME INFORMATIQUE, pour un profil Développeur (CV.pdf)."
        assert clean_text_for_tts(input_text) == expected

    def test_handles_empty_or_none(self):
        """Empty string or None must return empty string."""
        assert clean_text_for_tts("") == ""
        assert clean_text_for_tts(None) == ""
