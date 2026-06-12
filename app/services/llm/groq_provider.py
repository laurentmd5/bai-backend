import asyncio
from typing import Optional

from groq import AsyncGroq
import groq

from app.services.interfaces.llm_provider import ILLMProvider
from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import (
    LLMException,
    LLMTimeoutException,
    LLMUnavailableException,
)

logger = get_logger(__name__)


class GroqProvider(ILLMProvider):
    """
    Groq LLM Provider implementation for BARROW.AI POC.
    Used as the ultra-fast fallback provider (Llama 3.3 70B).
    """

    # We use llama-3.3-70b-versatile which is Groq's flagship open model
    # offering GPT-4 class performance at ~700 tokens/s.
    MODEL_NAME = "llama-3.3-70b-versatile"

    # Base system prompt to ensure consistent AI behavior
    SYSTEM_PROMPT_BAKED = """You are Barrow-AI, an official, professional, and friendly AI assistant for the National People's Party (NPP) of The Gambia.
Your goal is to answer questions politely and concisely using the provided context.
You MUST follow these rules:
1. Base your answer ONLY on the provided context. If the answer is not in the context, say politely that you don't have that information.
2. Maintain a respectful, neutral, and helpful tone.
3. Keep answers concise but complete.
4. EXPLICITLY CITE THE SOURCE when using context, using the exact format: [Source: <document_name>, <section>]
5. Conclude your responses with: "Ask. Know. Decide. - One Gambia. One People. One Barrow."
"""

    def __init__(self):
        self.api_key = settings.GROQ_API_KEY.get_secret_value() if settings.GROQ_API_KEY else None
        if not self.api_key:
            logger.warning("Groq API key is not configured. GroqProvider will fail on generation.")
            self.client = None
        else:
            self.client = AsyncGroq(
                api_key=self.api_key,
                max_retries=2,
                timeout=15.0
            )

    async def generate(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        language: str = "en",
    ) -> str:
        """
        Generate a response using Groq.
        """
        if not self.client:
            raise LLMUnavailableException("Groq API key not configured")

        try:
            messages = []
            
            # System prompt
            final_system_prompt = system_prompt if system_prompt else self.SYSTEM_PROMPT_BAKED
            messages.append({"role": "system", "content": final_system_prompt})

            # User prompt with context
            full_prompt = prompt
            if context:
                full_prompt = (
                    f"Context information is below.\n"
                    f"---------------------\n"
                    f"{context}\n"
                    f"---------------------\n"
                    f"Given the context information, answer the following query: {prompt}\n"
                    f"Please answer in {language}."
                )
            
            messages.append({"role": "user", "content": full_prompt})

            response = await self.client.chat.completions.create(
                model=self.MODEL_NAME,
                messages=messages,
                temperature=temperature if temperature is not None else 0.1,
                max_tokens=max_tokens or 1024,
                top_p=0.9,
            )

            if not response.choices:
                raise LLMException("Empty response from Groq")

            content = response.choices[0].message.content
            if not content:
                raise LLMException("Empty content from Groq")
                
            return content.strip()

        except groq.APITimeoutError as e:
            logger.error("groq_timeout_error", error=str(e))
            raise LLMTimeoutException("Groq API request timed out") from e
        except groq.RateLimitError as e:
            logger.error("groq_rate_limit_error", error=str(e))
            raise LLMException("Groq API rate limit exceeded") from e
        except groq.APIConnectionError as e:
            logger.error("groq_connection_error", error=str(e))
            raise LLMUnavailableException(f"Groq API connection error: {e}") from e
        except groq.APIError as e:
            logger.error("groq_api_error", error=str(e), status_code=e.status_code)
            raise LLMException(f"Groq API error: {e.message}") from e
        except Exception as e:
            logger.error("groq_unexpected_error", error=str(e))
            raise LLMException(f"Unexpected error calling Groq: {e}") from e

    async def generate_with_retry(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_retries: int = 2,
        **kwargs
    ) -> str:
        """
        Generate a response with automatic retry on failure.
        """
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    await asyncio.sleep(1.0 * attempt)  # Exponential backoff
                return await self.generate(
                    prompt=prompt,
                    context=context,
                    system_prompt=system_prompt,
                    **kwargs
                )
            except (LLMTimeoutException, LLMUnavailableException) as e:
                logger.warning("groq_generation_retry", attempt=attempt+1, error=str(e))
                last_error = e
            except Exception as e:
                # Don't retry on other errors
                raise e
                
        raise last_error or LLMException("Failed after retries")

    async def is_available(self) -> bool:
        """Check if Groq API is available."""
        return self.client is not None

    def get_model_name(self) -> str:
        """Get current model name."""
        return self.MODEL_NAME

    def get_provider_name(self) -> str:
        """Get provider name."""
        return "groq"

    async def count_tokens(self, text: str) -> int:
        """
        Count tokens using a simple approximation (1 token ~= 4 chars)
        as Groq doesn't provide a direct token counting endpoint.
        """
        return len(text) // 4
