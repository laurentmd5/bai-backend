"""
Tests for input normalization for low-literacy and short message handling.
"""

import pytest
from app.services.validation.input_validator import InputValidator


class TestInputNormalization:
    
    @pytest.fixture
    def validator(self):
        return InputValidator()
    
    def test_sms_abbreviations_english(self, validator):
        """Test expansion of SMS abbreviations."""
        assert "you" in validator.normalize_user_input("u")
        assert "Great" in validator.normalize_user_input("gr8")
        assert "Thanks" in validator.normalize_user_input("thx")
        assert "Before" in validator.normalize_user_input("b4")
        assert "Please" in validator.normalize_user_input("pls")
    
    def test_sms_abbreviations_french(self, validator):
        """Test expansion of French SMS abbreviations."""
        result = validator.normalize_user_input("stp", language="fr")
        assert "S'il te plaît" in result or "S'il vous plaît" in result
        assert "Beaucoup" in validator.normalize_user_input("bcp", language="fr")
        assert "Désolé" in validator.normalize_user_input("dsl", language="fr")
    
    def test_local_acronyms_expansion(self, validator):
        """Test expansion of local Gambian acronyms."""
        assert "National people's party" in validator.normalize_user_input("npp")
        assert "Information technology" in validator.normalize_user_input("it")
        assert "Information and communication technology" in validator.normalize_user_input("ict")
    
    def test_keyword_mapping_to_full_questions(self, validator):
        """Test that single keywords map to full questions."""
        assert "What has NPP done for internet" in validator.normalize_user_input("internet")
        assert "What are NPP plans for agriculture" in validator.normalize_user_input("agriculture")
        assert "What healthcare reforms" in validator.normalize_user_input("health")
        assert "What is NPP plan for education" in validator.normalize_user_input("education")
    
    def test_spell_corrections(self, validator):
        """Test common spelling corrections."""
        assert "internet" in validator.normalize_user_input("intrnet")
        assert "agriculture" in validator.normalize_user_input("agrikultur")
        assert "education" in validator.normalize_user_input("eduka")
        assert "Barrow" in validator.normalize_user_input("barow")
    
    def test_ultra_short_messages(self, validator):
        """Test handling of very short messages."""
        result = validator.normalize_user_input("")
        assert "help" in result.lower() or "ask" in result.lower()
        
        result = validator.normalize_user_input("?")
        assert "ask" in result.lower() or "help" in result.lower()
    
    def test_multiple_punctuation_removal(self, validator):
        """Test removal of duplicate punctuation."""
        assert "!!" not in validator.normalize_user_input("Help!!")
        assert "..." not in validator.normalize_user_input("What...")
        assert "??" not in validator.normalize_user_input("Really??")
    
    def test_whitespace_normalization(self, validator):
        """Test whitespace cleanup."""
        result = validator.normalize_user_input("too   many    spaces")
        assert "   " not in result
        assert "  " not in result
    
    def test_preserves_question_mark(self, validator):
        """Test that question marks are preserved correctly."""
        result = validator.normalize_user_input("what has npp done")
        assert result.endswith("?")
    
    def test_combined_sms_and_acronym(self, validator):
        """Test combining SMS abbreviations with acronym expansion."""
        result = validator.normalize_user_input("u know npp")
        assert "You" in result
        assert "national people's party" in result
    
    def test_case_preservation_in_acronyms(self, validator):
        """Test that acronyms are expanded correctly regardless of case."""
        result_lower = validator.normalize_user_input("npp")
        result_upper = validator.normalize_user_input("NPP")
        assert "National people's party" in result_lower
        # The result should be capitalized
        assert "National" in result_upper or "national" in result_upper.lower()


class TestDetectIntentFix:
    
    @pytest.fixture
    def validator(self):
        from app.services.chat_service import ChatService
        from app.repositories.session_repository import SessionRepository
        from app.repositories.conversation_repository import ConversationRepository
        
        # Create minimal mock repos
        class MockSessionRepo:
            pass
        
        class MockConversationRepo:
            pass
        
        chat_service = ChatService(
            session_repository=MockSessionRepo(),
            conversation_repository=MockConversationRepo()
        )
        return chat_service
    
    def test_no_false_positive_hi_in_lahido(self, validator):
        """Test that 'hi' in 'lahido' doesn't trigger greeting intent."""
        intent, keyword = validator._detect_intent("lahido")
        assert intent != "greeting", "BUG: 'hi' in 'Lahido' should not trigger greeting intent"
    
    def test_exact_hi_still_triggers_greeting(self, validator):
        """Test that standalone 'hi' still triggers greeting intent."""
        intent, keyword = validator._detect_intent("hi")
        assert intent == "greeting", "'hi' as standalone word should trigger greeting"
    
    def test_hi_with_word_boundaries(self, validator):
        """Test word boundaries in intent detection."""
        # "hi" should trigger greeting
        intent, keyword = validator._detect_intent("hi there")
        assert intent == "greeting"
        
        # "hi" inside a word should NOT trigger greeting
        intent, keyword = validator._detect_intent("calling")
        assert intent != "greeting"
    
    def test_ultra_short_messages_trigger_help(self, validator):
        """Test that very short messages trigger help intent."""
        intent, keyword = validator._detect_intent("hi")
        # After fix, this could be "help" for ultra-short or "greeting" for exact match
        assert intent in ["greeting", "help"]
        
        intent, keyword = validator._detect_intent("?")
        assert intent == "help"


class TestKeywordQueries:
    
    @pytest.fixture
    def validator(self):
        from app.services.chat_service import ChatService
        from app.repositories.session_repository import SessionRepository
        from app.repositories.conversation_repository import ConversationRepository
        
        class MockSessionRepo:
            pass
        
        class MockConversationRepo:
            pass
        
        chat_service = ChatService(
            session_repository=MockSessionRepo(),
            conversation_repository=MockConversationRepo()
        )
        return chat_service
    
    def test_keyword_query_recognition(self, validator):
        """Test that keyword queries are recognized."""
        import asyncio
        
        async def run_test():
            response = await validator._handle_keyword_query("internet", "en", "test-session")
            assert response is not None
            assert "113%" in response["message"] or "mobile" in response["message"]
            
            response = await validator._handle_keyword_query("agriculture", "en", "test-session")
            assert response is not None
            assert "farming" in response["message"].lower() or "rice" in response["message"].lower()
        
        asyncio.run(run_test())
    
    def test_keyword_query_language_support(self, validator):
        """Test that keyword queries support multiple languages."""
        import asyncio
        
        async def run_test():
            response_en = await validator._handle_keyword_query("npp", "en", "test-session")
            response_fr = await validator._handle_keyword_query("npp", "fr", "test-session")
            
            assert response_en is not None
            assert response_fr is not None
            assert response_en["message"] != response_fr["message"]
        
        asyncio.run(run_test())


class TestNormalizationIntegration:
    
    @pytest.fixture
    def validator(self):
        return InputValidator()
    
    def test_full_normalization_pipeline(self, validator):
        """Test the full normalization pipeline with a complex input."""
        # Input: SMS abbreviations + acronym + spelling mistakes + short message
        input_text = "u have any info on npp?"
        result = validator.normalize_user_input(input_text)
        
        # Should expand abbreviations and acronyms
        assert "You" in result
        assert "national people's party" in result
        assert "?" in result
    
    def test_keyword_expansion_with_misspellings(self, validator):
        """Test keyword expansion works even with misspellings."""
        # Misspelled "health"
        result = validator.normalize_user_input("helth")
        # Should correct to a meaningful question
        assert "?" in result or "health" in result.lower()
    
    def test_empty_and_minimal_inputs(self, validator):
        """Test handling of empty and minimal inputs."""
        result = validator.normalize_user_input("")
        assert len(result) > 0
        assert "help" in result.lower() or "ask" in result.lower()
        
        result = validator.normalize_user_input("  ")
        assert len(result) > 0
        assert "help" in result.lower() or "ask" in result.lower()
