import asyncio
import time
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
    LLMRateLimitException,
)
from app.services.llm.prompts import get_system_prompt

logger = get_logger(__name__)


class GroqProvider(ILLMProvider):
    """
    Groq LLM Provider implementation for Company Bot.
    Used as the ultra-fast primary provider with instant circuit-breaker on 429.
    """

    DEFAULT_MODEL = "openai/gpt-oss-20b"
    FALLBACK_MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
    MODEL_NAME = getattr(settings, "GROQ_MODEL", DEFAULT_MODEL)

    def __init__(self):
        self.api_key = settings.GROQ_API_KEY.get_secret_value() if settings.GROQ_API_KEY else None
        self.model = getattr(settings, "GROQ_MODEL", self.DEFAULT_MODEL)
        self._rate_limited_until: float = 0.0
        self._cooldown_seconds: float = getattr(settings, "GROQ_COOLDOWN_SECONDS", 60.0)
        self._timeout: float = getattr(settings, "GROQ_TIMEOUT", 7.0)

        if not self.api_key:
            logger.warning("Groq API key is not configured. GroqProvider will fail on generation.")
            self.client = None
        else:
            # CRITICAL: max_retries=0 prevents the Groq SDK from sleeping 5-15s internally on 429
            # Timeout is 7.0s so stalled requests fail fast rather than hanging 15s+
            self.client = AsyncGroq(
                api_key=self.api_key,
                max_retries=0,
                timeout=self._timeout
            )

    def is_rate_limited(self) -> bool:
        """Check if Groq is currently in a 429 Rate Limit cooldown window."""
        return time.time() < self._rate_limited_until

    def mark_rate_limited(self, retry_after: Optional[float] = None) -> None:
        """Open the circuit breaker for Groq to immediately bypass it on future calls."""
        cooldown = retry_after if (retry_after and retry_after > 0) else self._cooldown_seconds
        self._rate_limited_until = time.time() + cooldown
        logger.warning(
            "groq_circuit_breaker_opened_due_to_429",
            cooldown_seconds=cooldown,
            resume_at_epoch=self._rate_limited_until,
        )


    async def generate(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        language: str = "en",
        history: str = "",
    ) -> str:
        """
        Generate a response using Groq.
        """
        if not self.client:
            raise LLMUnavailableException("Groq API key not configured")

        # Fast circuit-breaker check: if Groq is in 429 cooldown, do not make network calls!
        if self.is_rate_limited():
            remaining = max(1, int(self._rate_limited_until - time.time()))
            logger.warning("groq_fast_bypassed_active_cooldown", remaining_seconds=remaining)
            raise LLMRateLimitException(
                f"Groq API rate limit cooldown active ({remaining}s remaining)",
                retry_after=remaining
            )

        try:
            messages = []
            
            # System prompt
            final_system_prompt = system_prompt if system_prompt else get_system_prompt(language)
            
            context_text = context if context else "No specific context available."
            history_text = history if history else "No previous conversation."
            
            full_system_prompt = final_system_prompt.replace("{context}", context_text).replace("{history}", history_text).replace("{question}", prompt)
            
            messages.append({"role": "system", "content": full_system_prompt})

            # User prompt
            # If the system prompt didn't contain {question}, append it to the user message
            if "{question}" not in final_system_prompt:
                user_msg = f"Context:\n{context_text}\n\nQuestion: {prompt}\nPlease answer in {language}."
            else:
                user_msg = prompt

            messages.append({"role": "user", "content": user_msg})
            
            # Determine candidate models to try: self.model first, then FALLBACK_MODELS
            models_to_try = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]
            response = None
            last_api_error = None

            for candidate_model in models_to_try:
                try:
                    response = await self.client.chat.completions.create(
                        model=candidate_model,
                        messages=messages,
                        temperature=temperature if temperature is not None else 0.1,
                        max_tokens=max_tokens or 1024,
                        top_p=0.9,
                    )
                    if candidate_model != self.model:
                        logger.info(
                            "groq_switched_to_working_model",
                            previous_model=self.model,
                            new_model=candidate_model,
                        )
                        self.model = candidate_model
                    break
                except groq.RateLimitError as e:
                    # Rate limit is account-wide: trying other models is useless and adds latency.
                    # Raise immediately so the outer handler trips the circuit breaker.
                    raise e
                except groq.APIError as e:
                    if getattr(e, "status_code", None) == 404 or "model_not_found" in str(e).lower():
                        logger.warning(
                            "groq_model_unavailable_trying_fallback",
                            model=candidate_model,
                            error=str(e),
                        )
                        last_api_error = e
                        continue
                    raise e

            if response is None:
                if last_api_error:
                    raise last_api_error
                raise LLMException("Groq generation failed with all candidate models")


            if not response.choices:
                raise LLMException("Empty response from Groq")

            content = response.choices[0].message.content
            if not content:
                raise LLMException("Empty content from Groq")
                
            return content.strip()

        except groq.RateLimitError as e:
            # 429 Too Many Requests: trip the circuit breaker and raise LLMRateLimitException immediately
            retry_after = None
            try:
                if hasattr(e, "response") and e.response and hasattr(e.response, "headers"):
                    raw_ra = e.response.headers.get("retry-after")
                    if raw_ra:
                        retry_after = float(raw_ra)
            except Exception:
                pass
            self.mark_rate_limited(retry_after)
            logger.error("groq_rate_limit_error_triggered_circuit_breaker", error=str(e), retry_after=retry_after)
            raise LLMRateLimitException("Groq API rate limit exceeded (HTTP 429)", retry_after=retry_after) from e
        except groq.APITimeoutError as e:
            logger.error("groq_timeout_error", error=str(e))
            raise LLMTimeoutException(int(self._timeout)) from e
        except groq.APIConnectionError as e:
            logger.error("groq_connection_error", error=str(e))
            raise LLMUnavailableException(f"Groq API connection error: {e}") from e
        except groq.APIError as e:
            logger.error("groq_api_error", error=str(e), status_code=getattr(e, "status_code", None))
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
        CRITICAL: Never retries on 429 RateLimit to allow immediate 0s fallback to Gemini.
        """
        last_error = None
        history = kwargs.pop("history", "")
        language = kwargs.pop("language", "en")
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    await asyncio.sleep(1.0 * attempt)  # Exponential backoff
                return await self.generate(
                    prompt=prompt,
                    context=context,
                    system_prompt=system_prompt,
                    history=history,
                    language=language,
                    **kwargs
                )
            except LLMRateLimitException:
                # NEVER retry on 429: quota is exhausted, retrying only adds latency. Fail immediately!
                raise
            except (LLMTimeoutException, LLMUnavailableException) as e:
                logger.warning("groq_generation_retry", attempt=attempt+1, error=str(e))
                last_error = e
            except Exception as e:
                # Don't retry on other errors
                raise e
                
        raise last_error or LLMException("Failed after retries")

    async def is_available(self) -> bool:
        """Check if Groq API is available and not in active rate-limit cooldown."""
        if not self.client:
            return False
        if self.is_rate_limited():
            return False
        return True

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

