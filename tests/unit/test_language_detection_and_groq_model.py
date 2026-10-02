"""
Unit tests for language detection accuracy and Groq model resilience.
Verifies that:
1. 'Comment vas-tu ?' and other conversational French phrases are accurately detected as 'fr'.
2. English questions are accurately detected as 'en'.
3. GroqProvider defaults to 'openai/gpt-oss-20b' and fails over gracefully on 404.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.validation.input_validator import InputValidator
from app.services.llm.groq_provider import GroqProvider
import groq


def test_detect_language_french_variations():
    """Verify common French greetings, questions, and hyphenated expressions detect as French."""
    validator = InputValidator()

    # The exact phrase reported by user
    assert validator.detect_language("Comment vas-tu ?") == "fr"
    assert validator.detect_language("comment vas tu") == "fr"
    assert validator.detect_language("Comment allez-vous ?") == "fr"
    assert validator.detect_language("Bonjour, j'ai besoin de caméras de surveillance") == "fr"
    assert validator.detect_language("Quel est le prix pour une installation réseau ?") == "fr"
    assert validator.detect_language("Est-ce que vous proposez du cloud ?") == "fr"
    assert validator.detect_language("Merci pour votre aide") == "fr"
    assert validator.detect_language("Je cherche un stage en développement web") == "fr"


def test_detect_language_english_variations():
    """Verify standard English queries detect as English."""
    validator = InputValidator()

    assert validator.detect_language("Hello, how are you?") == "en"
    assert validator.detect_language("What services do you offer?") == "en"
    assert validator.detect_language("Could you please provide a quote for cloud hosting?") == "en"
    assert validator.detect_language("Can I send my resume for the job position?") == "en"


def test_groq_provider_default_model_is_valid():
    """Verify GroqProvider uses the active modern model instead of deprecated llama-3.1-8b-instant."""
    provider = GroqProvider()
    assert provider.model == "openai/gpt-oss-20b"
    assert "openai/gpt-oss-20b" in provider.FALLBACK_MODELS


@pytest.mark.asyncio
async def test_groq_provider_fallback_when_model_returns_404():
    """Verify GroqProvider falls back to alternative model if the configured one returns 404."""
    provider = GroqProvider()
    provider.client = MagicMock()

    # Simulate 404 APIError on first model, success on second
    api_error_404 = groq.APIError(
        message="The model does not exist or you do not have access to it.",
        request=MagicMock(),
        body={"error": {"code": "model_not_found"}}
    )
    api_error_404.status_code = 404

    success_response = MagicMock()
    success_response.choices = [MagicMock()]
    success_response.choices[0].message.content = "Bonjour ! Je vais très bien, comment puis-je vous aider ?"

    provider.client.chat.completions.create = AsyncMock(
        side_effect=[api_error_404, success_response]
    )

    # Force starting model to a decommissioned name
    provider.model = "llama-3.1-8b-instant"

    response = await provider.generate(
        prompt="Comment vas-tu ?",
        language="fr"
    )

    assert "Bonjour" in response
    # The provider switched model to the working one
    assert provider.model == "openai/gpt-oss-20b"
    assert provider.client.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_groq_provider_rate_limit_429_trips_circuit_breaker_immediately():
    """Verify that HTTP 429 immediately raises LLMRateLimitException and opens circuit breaker."""
    from app.core.exceptions import LLMRateLimitException
    import groq

    provider = GroqProvider()
    provider.client = MagicMock()

    # Simulate HTTP 429 RateLimitError with a 30s Retry-After
    rate_limit_err = groq.RateLimitError(
        message="Rate limit reached for model `openai/gpt-oss-20b` in organization `org_xxx` on tokens per minute (TPM).",
        response=MagicMock(headers={"retry-after": "30"}),
        body={"error": {"message": "Rate limit exceeded", "type": "tokens"}}
    )
    provider.client.chat.completions.create = AsyncMock(side_effect=rate_limit_err)

    # 1. First call: must raise LLMRateLimitException immediately (no retry loop on alternative models)
    with pytest.raises(LLMRateLimitException) as exc_info:
        await provider.generate_with_retry(
            prompt="Quel est votre devis pour caméras ?",
            language="fr",
            max_retries=2
        )

    assert "429" in str(exc_info.value) or "rate limit" in str(exc_info.value).lower()
    # Called exactly once: did not attempt retries on 429
    assert provider.client.chat.completions.create.await_count == 1
    # Circuit breaker is tripped
    assert provider.is_rate_limited() is True
    assert await provider.is_available() is False

    # 2. Second call while circuit breaker is open: should fail instantly (0 network calls)
    with pytest.raises(LLMRateLimitException) as exc_info2:
        await provider.generate(prompt="Autre question", language="fr")

    assert "cooldown active" in str(exc_info2.value).lower()
    # Call count still 1: network was completely bypassed
    assert provider.client.chat.completions.create.await_count == 1
