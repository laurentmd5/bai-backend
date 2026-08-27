"""
Tests for input normalization for low-literacy and short message handling.
"""

import pytest
from unittest.mock import MagicMock
from app.services.validation.input_validator import InputValidator


class TestInputNormalization:
    
    @pytest.fixture
    def validator(self):
        return InputValidator()
    
    @pytest.mark.asyncio
    async def test_sms_abbreviations_english(self, validator):
        """Test expansion of SMS abbreviations."""
        assert "you" in await validator.normalize_user_input("u")
        assert "Great" in await validator.normalize_user_input("gr8")
        assert "Thanks" in await validator.normalize_user_input("thx")
        assert "Before" in await validator.normalize_user_input("b4")
        assert "Please" in await validator.normalize_user_input("pls")
    
    @pytest.mark.asyncio
    async def test_sms_abbreviations_french(self, validator):
        """Test expansion of French SMS abbreviations."""
        result = await validator.normalize_user_input("stp", language="fr")
        assert "s'il te plaît" in result.lower() or "s'il vous plaît" in result.lower()
        assert "beaucoup" in (await validator.normalize_user_input("bcp", language="fr")).lower()
        assert "désolé" in (await validator.normalize_user_input("dsl", language="fr")).lower()
    
    @pytest.mark.asyncio
    async def test_local_acronyms_expansion(self, validator):
        """Test expansion of acronyms."""
        assert "information technology" in (await validator.normalize_user_input("it")).lower()
        assert "information and communication technology" in (await validator.normalize_user_input("ict")).lower()
    
    @pytest.mark.asyncio
    async def test_spell_corrections(self, validator):
        """Test common spelling corrections."""
        assert "internet" in (await validator.normalize_user_input("intrnet")).lower()
        assert "agriculture" in (await validator.normalize_user_input("agrikultur")).lower()
        assert "education" in (await validator.normalize_user_input("eduka")).lower()
    
    @pytest.mark.asyncio
    async def test_ultra_short_messages(self, validator):
        """Test handling of very short messages."""
        result = await validator.normalize_user_input("")
        assert "help" in result.lower() or "ask" in result.lower()
        
        result = await validator.normalize_user_input("?")
        assert "help" in result.lower() or "ask" in result.lower()
    
    @pytest.mark.asyncio
    async def test_multiple_punctuation_removal(self, validator):
        """Test removal of duplicate punctuation."""
        res1 = await validator.normalize_user_input("Help!!")
        assert "!!" not in res1
        res2 = await validator.normalize_user_input("What...")
        assert "..." not in res2
        res3 = await validator.normalize_user_input("Really??")
        assert "??" not in res3
    
    @pytest.mark.asyncio
    async def test_whitespace_normalization(self, validator):
        """Test whitespace cleanup."""
        result = await validator.normalize_user_input("too   many    spaces")
        assert "   " not in result
        assert "  " not in result
    
    @pytest.mark.asyncio
    async def test_preserves_question_mark(self, validator):
        """Test that question marks are preserved correctly."""
        result = await validator.normalize_user_input("what services do you offer")
        assert result.endswith("?")
    
    @pytest.mark.asyncio
    async def test_combined_sms_and_acronym(self, validator):
        """Test combining SMS abbreviations with acronym expansion."""
        result = await validator.normalize_user_input("u know ict")
        assert "you" in result.lower()
        assert "information and communication technology" in result.lower()


class TestDetectIntentFix:
    
    @pytest.fixture
    def chat_service(self):
        from app.services.chat_service import ChatService
        
        mock_session_repo = MagicMock()
        mock_conv_repo = MagicMock()
        mock_rag_service = MagicMock()
        
        return ChatService(
            session_repository=mock_session_repo,
            conversation_repository=mock_conv_repo,
            rag_service=mock_rag_service
        )
    
    def test_no_false_positive_hi_in_word(self, chat_service):
        """Test that 'hi' inside a word doesn't trigger greeting intent."""
        intent, keyword = chat_service._detect_intent("thisword")
        assert intent != "greeting"
    
    def test_exact_hi_still_triggers_greeting(self, chat_service):
        """Test that standalone 'hi' still triggers greeting intent."""
        intent, keyword = chat_service._detect_intent("hi")
        assert intent == "greeting"
    
    def test_hi_with_word_boundaries(self, chat_service):
        """Test word boundaries in intent detection."""
        intent, keyword = chat_service._detect_intent("bonjour")
        assert intent == "greeting"
        
        intent, keyword = chat_service._detect_intent("calling")
        assert intent != "greeting"
    
    def test_ultra_short_messages_trigger_help(self, chat_service):
        """Test that very short messages trigger help intent."""
        intent, keyword = chat_service._detect_intent("?")
        assert intent == "help"


class TestNormalizationIntegration:
    
    @pytest.fixture
    def validator(self):
        return InputValidator()
    
    @pytest.mark.asyncio
    async def test_full_normalization_pipeline(self, validator):
        """Test the full normalization pipeline with a complex input."""
        input_text = "u have any info on ict?"
        result = await validator.normalize_user_input(input_text)
        
        assert "you" in result.lower()
        assert "information and communication technology" in result.lower()
        assert "?" in result
    
    @pytest.mark.asyncio
    async def test_empty_and_minimal_inputs(self, validator):
        """Test handling of empty and minimal inputs."""
        result = await validator.normalize_user_input("")
        assert len(result) > 0
        assert "help" in result.lower() or "ask" in result.lower()
        
        result = await validator.normalize_user_input("  ")
        assert len(result) > 0
        assert "help" in result.lower() or "ask" in result.lower()

