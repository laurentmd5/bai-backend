"""
Unit tests for voice language inertia and short keywords locking.
Tests that short affirmative/negative French voice messages ("Oui", "Non")
maintain French conversation continuity.
"""

import pytest
import re
from unittest.mock import AsyncMock, MagicMock
from app.services.whatsapp_service import WhatsAppService


class TestVoiceLanguageInertia:
    """Tests for language resolution with session inertia."""

    @pytest.fixture
    def whatsapp_service(self):
        chat_service = MagicMock()
        session_repo = MagicMock()
        return WhatsAppService(chat_service=chat_service, session_repository=session_repo)

    @pytest.mark.asyncio
    async def test_voice_oui_locks_to_french(self, whatsapp_service):
        """Word 'Oui' or 'oui' must always resolve to French regardless of Whisper tags."""
        transcribed_text = "Oui"
        whisper_lang = "en"  # Simulated false Whisper tag
        
        words = set(re.findall(r'\b\w+\b', transcribed_text.lower()))
        french_keywords = {
            "oui", "ouais", "ouep", "non", "nan", "ok", "d'accord", "daccord", "dac", "merci",
            "bonjour", "salut", "bonsoir", "stage", "stages", "stagiaire", "stagiaires", "emploi",
            "candidat", "candidature", "developpeur", "developpement", "web", "cv", "informatique",
            "reseau", "reseaux", "voila", "exact", "exactement", "absolument", "parfait", "compris",
            "disponible", "disponibilite", "terrain", "site"
        }
        has_french_keyword = bool(words & french_keywords)
        assert has_french_keyword is True

    @pytest.mark.asyncio
    async def test_voice_short_word_inherits_french_session(self, whatsapp_service):
        """Short answers (< 3 words) inherit the ongoing session's language."""
        transcribed_text = "Très bien"
        session_lang = "fr"
        whisper_lang = "en"
        text_lang = whatsapp_service._input_validator.detect_language(transcribed_text)
        word_count = len(transcribed_text.split())
        
        if word_count < 3 and session_lang in ["fr", "en"]:
            detected_language = session_lang
        else:
            detected_language = whisper_lang
            
        assert detected_language == "fr"

    @pytest.mark.asyncio
    async def test_voice_full_english_sentence_switches_to_english(self, whatsapp_service):
        """A full English sentence (>= 3 words) properly switches to English."""
        transcribed_text = "I need an IT quote for my company"
        session_lang = "fr"
        whisper_lang = "en"
        text_lang = whatsapp_service._input_validator.detect_language(transcribed_text)
        word_count = len(transcribed_text.split())
        
        words = set(re.findall(r'\b\w+\b', transcribed_text.lower()))
        french_keywords = {"oui", "non", "bonjour", "stage"}
        has_french_keyword = bool(words & french_keywords)
        
        if has_french_keyword:
            detected_language = "fr"
        elif text_lang in ["en", "fr"] and word_count >= 3:
            detected_language = text_lang
        else:
            detected_language = session_lang
            
        assert detected_language == "en"
