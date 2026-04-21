"""
Gemini LLM Provider implementation for BARROW.AI.
Integrates with Google Gemini 3.0 Flash fine-tuned model.
"""

import asyncio
from typing import Optional, List, Dict, Any
import hashlib

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from app.services.interfaces.llm_provider import ILLMProvider
from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import (
    LLMException,
    LLMTimeoutException,
    LLMUnavailableException,
    BarrowAIException,
    ErrorCode,
)

logger = get_logger(__name__)


class GeminiException(LLMException):
    """Gemini-specific LLM exception."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, original_error: Optional[Exception] = None):
        super().__init__(
            message=f"Gemini API error: {message}",
            code=ErrorCode.LLM_UNAVAILABLE,
            status_code=503,
            details={
                "provider": "gemini",
                "status_code": status_code,
                "original_error": str(original_error) if original_error else None
            }
        )
        self.gemini_status_code = status_code


class GeminiQuotaExceededException(GeminiException):
    """Raised when Gemini quota is exceeded."""
    
    def __init__(self):
        super().__init__(
            message="Gemini API quota exceeded",
            status_code=429
        )


class GeminiTimeoutException(LLMTimeoutException):
    """Gemini-specific timeout exception."""
    
    def __init__(self, timeout_seconds: int):
        super().__init__(timeout_seconds)
        self.details["provider"] = "gemini"


class GeminiProvider(ILLMProvider):
    """
    Google Gemini 3.0 Flash LLM provider implementation.
    
    Uses the fine-tuned model askbarrow-npp-v3 for campaign-specific responses.
    Implements retry logic, circuit breaker pattern, and graceful degradation.
    """
    
    # System prompt integrated into the fine-tuned model
    # This is the baked-in prompt that defines the assistant's behavior
    SYSTEM_PROMPT_BAKED = """You are AskBarrow.ai, the OFFICIAL campaign assistant for President Adama Barrow and the NPP of The Gambia.

ABSOLUTE RULES (NON-NEGOTIABLE):
1. Answer ONLY using the information provided in the context below.
2. If the context does NOT contain the information, respond EXACTLY: "I do not have this information in my campaign database. Please visit www.npp.gm or contact the nearest PACE office."
3. NEVER criticize President Barrow or the NPP. Never praise the opposition.
4. NEVER make undocumented political promises.
5. ALWAYS end with: "Ask. Know. Decide. - One Gambia. One People. One Barrow."
6. Be respectful, professional, and positive about The Gambia's achievements.

CONTEXT (official NPP documents):
{context}

QUESTION: {question}
ANSWER:"""
    
    FALLBACK_MESSAGES = {
        "en": (
            "I am experiencing a temporary technical issue. "
            "Please try again in a few moments or visit www.npp.gm for more information.\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "fr": (
            "Je rencontre une difficulté technique momentanée. "
            "Veuillez réessayer dans quelques instants ou visiter www.npp.gm.\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
    }
    
    def __init__(self):
        self._api_key = settings.gemini_api_key_str
        self._model = settings.GEMINI_MODEL
        self._base_url = "https://generativelanguage.googleapis.com/v1beta"
        self._timeout = settings.GEMINI_TIMEOUT
        self._temperature = settings.GEMINI_TEMPERATURE
        self._max_tokens = settings.GEMINI_MAX_TOKENS
        self._client: Optional[httpx.AsyncClient] = None
        self._circuit_open = False
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._circuit_threshold = 5
        self._circuit_reset_seconds = 60
    
    async def _get_client(self) -> httpx.AsyncClient:
        """
        Get or create an HTTP client with connection pooling.
        
        Returns:
            Configured httpx AsyncClient
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=self._timeout,
                    write=10.0,
                    pool=10.0,
                ),
                limits=httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20,
                    keepalive_expiry=30.0,
                ),
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self._api_key,
                },
            )
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    def _check_circuit_breaker(self) -> None:
        """
        Check if circuit breaker is open.
        
        Raises:
            GeminiException: If circuit is open
        """
        import time
        
        if not self._circuit_open:
            return
        
        if self._last_failure_time:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self._circuit_reset_seconds:
                logger.info("gemini_circuit_breaker_half_open")
                self._circuit_open = False
                self._failure_count = 0
                return
        
        raise GeminiException(
            "Circuit breaker is open - Gemini temporarily unavailable",
            status_code=503
        )
    
    def _record_success(self) -> None:
        """Record a successful request and reset circuit breaker."""
        self._circuit_open = False
        self._failure_count = 0
        self._last_failure_time = None
    
    def _record_failure(self) -> None:
        """Record a failed request and potentially open circuit breaker."""
        import time
        
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._failure_count >= self._circuit_threshold:
            self._circuit_open = True
            logger.error(
                "gemini_circuit_breaker_opened",
                failures=self._failure_count,
                threshold=self._circuit_threshold
            )
    
    def _build_full_prompt(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Build the complete prompt with context.
        
        Args:
            prompt: User question
            context: RAG context chunks
            system_prompt: Override system prompt (rarely used)
            
        Returns:
            Complete formatted prompt
        """
        if system_prompt:
            base_prompt = system_prompt
        else:
            base_prompt = self.SYSTEM_PROMPT_BAKED
        
        context_text = context if context else "No specific context available."
        
        return base_prompt.replace("{context}", context_text).replace("{question}", prompt)
    
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
        Generate a response using Gemini 3.0 Flash.
        
        Args:
            prompt: User question
            context: RAG context
            system_prompt: Optional system prompt override
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            language: Target language
            
        Returns:
            Generated response
            
        Raises:
            GeminiException: On API error
            GeminiTimeoutException: On timeout
            GeminiQuotaExceededException: On quota exceeded
        """
        self._check_circuit_breaker()
        
        temp = temperature if temperature is not None else self._temperature
        tokens = max_tokens if max_tokens is not None else self._max_tokens
        
        full_prompt = self._build_full_prompt(prompt, context, system_prompt)
        
        url = f"{self._base_url}/tunedModels/{self._model}:generateContent"
        
        payload = {
            "contents": [{
                "parts": [{"text": full_prompt}]
            }],
            "generationConfig": {
                "temperature": temp,
                "maxOutputTokens": tokens,
                "topP": 0.9,
                "topK": 40,
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
            ],
        }
        
        try:
            client = await self._get_client()
            
            logger.debug(
                "gemini_request_started",
                model=self._model,
                prompt_length=len(full_prompt),
                temperature=temp,
            )
            
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                
                if "candidates" not in data or not data["candidates"]:
                    raise GeminiException("No candidates in response")
                
                candidate = data["candidates"][0]
                
                if "content" not in candidate:
                    # Check if blocked by safety
                    if "finishReason" in candidate:
                        reason = candidate.get("finishReason")
                        if reason == "SAFETY":
                            raise GeminiException(f"Response blocked by safety filter: {reason}")
                    raise GeminiException("No content in candidate")
                
                generated_text = candidate["content"]["parts"][0]["text"]
                
                # Ensure slogan is present
                if "Ask. Know. Decide." not in generated_text:
                    generated_text += "\n\nAsk. Know. Decide. - One Gambia. One People. One Barrow."
                
                self._record_success()
                
                logger.debug(
                    "gemini_request_completed",
                    response_length=len(generated_text),
                    finish_reason=candidate.get("finishReason"),
                )
                
                return generated_text.strip()
                
            elif response.status_code == 429:
                self._record_failure()
                logger.error("gemini_quota_exceeded")
                raise GeminiQuotaExceededException()
                
            elif response.status_code >= 500:
                self._record_failure()
                error_data = response.json() if response.text else {}
                error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                raise GeminiException(error_msg, status_code=response.status_code)
                
            else:
                self._record_failure()
                error_data = response.json() if response.text else {}
                error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                raise GeminiException(error_msg, status_code=response.status_code)
                
        except httpx.TimeoutException as e:
            self._record_failure()
            logger.error("gemini_timeout", timeout=self._timeout)
            raise GeminiTimeoutException(self._timeout) from e
            
        except httpx.ConnectError as e:
            self._record_failure()
            logger.error("gemini_connection_error", error=str(e))
            raise GeminiException("Failed to connect to Gemini API", original_error=e) from e
            
        except (GeminiException, GeminiTimeoutException, GeminiQuotaExceededException):
            raise
            
        except Exception as e:
            self._record_failure()
            logger.error("gemini_unexpected_error", error=str(e), exc_info=True)
            raise GeminiException(f"Unexpected error: {str(e)}", original_error=e) from e
    
    async def generate_with_retry(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_retries: int = 2,
        **kwargs
    ) -> str:
        """
        Generate with automatic retry on transient failures.
        
        Args:
            prompt: User question
            context: RAG context
            system_prompt: System prompt override
            max_retries: Maximum retry attempts
            **kwargs: Additional generation parameters
            
        Returns:
            Generated response or fallback message
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                return await self.generate(
                    prompt=prompt,
                    context=context,
                    system_prompt=system_prompt,
                    **kwargs
                )
                
            except GeminiTimeoutException as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(
                        "gemini_retry_timeout",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait_time
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("gemini_max_retries_exceeded_timeout")
                    
            except (GeminiException, GeminiQuotaExceededException) as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = 1 * (2 ** attempt)
                    logger.warning(
                        "gemini_retry_error",
                        attempt=attempt + 1,
                        error=str(e),
                        wait_seconds=wait_time
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("gemini_max_retries_exceeded_error")
                    
            except Exception as e:
                last_error = e
                logger.error("gemini_unexpected_error_no_retry", error=str(e))
                break
        
        # Return fallback message
        language = kwargs.get("language", "en")
        return self.FALLBACK_MESSAGES.get(language, self.FALLBACK_MESSAGES["en"])
    
    async def is_available(self) -> bool:
        """
        Check if Gemini API is available.
        
        Returns:
            True if service is reachable
        """
        if self._circuit_open:
            return False
        
        try:
            client = await self._get_client()
            url = f"{self._base_url}/models?key={self._api_key}"
            response = await client.get(url)
            return response.status_code == 200
        except Exception as e:
            logger.warning("gemini_availability_check_failed", error=str(e))
            return False
    
    def get_model_name(self) -> str:
        """Get the current model name."""
        return self._model
    
    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "gemini"
    
    async def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Gemini uses approximately 4 characters per token for English text.
        This is a rough estimate since actual tokenization depends on the model.
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            Estimated token count
        """
        # Rough estimate: 4 chars per token for English
        return len(text) // 4