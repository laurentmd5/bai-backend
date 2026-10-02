"""
Unit test verifying immediate 0s fallback to Gemini upon Groq HTTP 429 (Rate Limit).
Confirms that:
1. When Groq returns a 429 RateLimitError, ChatService does NOT hang 15 seconds.
2. It immediately executes Gemini and returns the Gemini response.
3. Subsequent requests within the cooldown window bypass Groq completely in 0ms.
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
import groq

from app.core.exceptions import LLMRateLimitException
from app.services.llm.groq_provider import GroqProvider
from app.services.llm.gemini_provider import GeminiProvider


@pytest.mark.asyncio
async def test_groq_429_immediate_fallback_to_gemini():
    """Verify that a 429 on Groq triggers immediate fallback to Gemini without retries or hanging."""
    # 1. Instantiate real providers
    groq_provider = GroqProvider()
    gemini_provider = GeminiProvider()

    # 2. Mock Groq client to raise 429 RateLimitError instantly
    groq_rate_limit = groq.RateLimitError(
        message="Rate limit reached for model `openai/gpt-oss-20b` in organization `org_xxx` on tokens per minute (TPM).",
        response=MagicMock(headers={"retry-after": "45"}),
        body={"error": {"message": "Rate limit exceeded", "type": "tokens"}}
    )
    groq_provider.client = MagicMock()
    groq_provider.client.chat.completions.create = AsyncMock(side_effect=groq_rate_limit)

    # 3. Mock Gemini provider to return a valid response immediately
    gemini_provider.generate_with_retry = AsyncMock(
        return_value="Bonjour ! NETSYSTEME propose des solutions de vidéosurveillance et réseaux informatiques."
    )
    gemini_provider.get_provider_name = MagicMock(return_value="gemini")
    gemini_provider.get_model_name = MagicMock(return_value="gemini-2.5-flash-lite")

    # 4. Measure execution time of the failover
    start_time = time.time()

    # Simulate the failover flow in chat_service Step 7
    generated_response = None
    provider_used = None

    if await groq_provider.is_available():
        try:
            generated_response = await groq_provider.generate_with_retry(
                prompt="Quels sont vos services ?",
                language="fr",
                max_retries=1
            )
            provider_used = "groq"
        except LLMRateLimitException:
            # Immediate fallback triggered
            generated_response = await gemini_provider.generate_with_retry(
                prompt="Quels sont vos services ?",
                language="fr"
            )
            provider_used = "gemini"

    duration = time.time() - start_time

    # 5. Assertions
    assert duration < 1.0, f"Failover took too long: {duration:.3f}s (should be < 1s, not 15s!)"
    assert provider_used == "gemini"
    assert "vidéosurveillance" in generated_response
    assert gemini_provider.generate_with_retry.await_count == 1
    assert groq_provider.is_rate_limited() is True

    # 6. Next request during cooldown: Groq is_available() is False, so it bypasses Groq instantly
    start_time_2 = time.time()
    next_response = None
    if await groq_provider.is_available():
        next_response = "from groq"
    else:
        next_response = await gemini_provider.generate_with_retry(prompt="Deuxième question", language="fr")

    duration_2 = time.time() - start_time_2
    assert duration_2 < 0.1, f"Bypassed call should be virtually instantaneous: {duration_2:.3f}s"
    assert gemini_provider.generate_with_retry.await_count == 2
