"""
Ollama LLM Provider implementation for BARROW.AI.
Phase 2 provider for sovereign, local LLM inference.
"""

import asyncio
from typing import Optional, List, Dict, Any

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from app.services.interfaces.llm_provider import ILLMProvider
from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import (
    LLMException,
    LLMTimeoutException,
    LLMUnavailableException,
    ErrorCode,
)

logger = get_logger(__name__)


class OllamaException(LLMException):
    """Ollama-specific LLM exception."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            message=f"Ollama error: {message}",
            code=ErrorCode.LLM_UNAVAILABLE,
            status_code=503,
            details={
                "provider": "ollama",
                "original_error": str(original_error) if original_error else None
            }
        )


class OllamaTimeoutException(LLMTimeoutException):
    """Ollama-specific timeout exception."""
    
    def __init__(self, timeout_seconds: int):
        super().__init__(timeout_seconds)
        self.details["provider"] = "ollama"


class OllamaProvider(ILLMProvider):
    """
    Ollama LLM provider for local inference.
    
    Phase 2 implementation for sovereign AI operations.
    Uses Llama 3.2 3B or Mistral 7B models locally.
    """
    
    # System prompt for Ollama (not fine-tuned, so provided each request)
    SYSTEM_PROMPT = """You are AskBarrow.ai, the OFFICIAL campaign assistant for President Adama Barrow and the NPP of The Gambia.

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
            "Please try again in a few moments.\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "fr": (
            "Je rencontre une difficulté technique momentanée. "
            "Veuillez réessayer dans quelques instants.\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
    }
    
    def __init__(self):
        self._base_url = settings.ollama_url
        self._model = settings.OLLAMA_MODEL
        self._timeout = settings.GEMINI_TIMEOUT
        self._temperature = settings.GEMINI_TEMPERATURE
        self._max_tokens = settings.GEMINI_MAX_TOKENS
        self._client: Optional[httpx.AsyncClient] = None
        self._model_loaded = False
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=self._timeout,
                    write=10.0,
                    pool=10.0,
                ),
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    max_connections=10,
                ),
            )
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def _ensure_model_loaded(self) -> None:
        """
        Ensure the model is loaded in Ollama.
        Pulls the model if not present.
        """
        if self._model_loaded:
            return
        
        try:
            client = await self._get_client()
            
            # Check if model exists
            response = await client.get(f"{self._base_url}/api/tags")
            response.raise_for_status()
            
            data = response.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            
            if self._model in models:
                self._model_loaded = True
                logger.info("ollama_model_found", model=self._model)
                return
            
            # Pull model
            logger.info("ollama_pulling_model", model=self._model)
            response = await client.post(
                f"{self._base_url}/api/pull",
                json={"name": self._model, "stream": False},
                timeout=600.0,
            )
            response.raise_for_status()
            
            self._model_loaded = True
            logger.info("ollama_model_pulled", model=self._model)
            
        except Exception as e:
            logger.error("ollama_model_load_failed", model=self._model, error=str(e))
            raise OllamaException(f"Failed to load model {self._model}", e)
    
    def _build_prompt(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Build the complete prompt for Ollama.
        
        Ollama expects a single prompt string with system instructions included.
        """
        base_prompt = system_prompt if system_prompt else self.SYSTEM_PROMPT
        context_text = context if context else "No specific context available."
        
        full_prompt = base_prompt.replace("{context}", context_text).replace("{question}", prompt)
        
        # If the base_prompt didn't have {question}, the user prompt would be lost. Append it.
        if prompt not in full_prompt and "{question}" not in base_prompt:
            full_prompt = f"{full_prompt}\n\nRaw User Input: {prompt}"
            
        return full_prompt
    
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
        Generate a response using Ollama.
        
        Args:
            prompt: User question
            context: RAG context
            system_prompt: Optional system prompt override
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            language: Target language
            
        Returns:
            Generated response
        """
        await self._ensure_model_loaded()
        
        temp = temperature if temperature is not None else self._temperature
        tokens = max_tokens if max_tokens is not None else self._max_tokens
        
        full_prompt = self._build_prompt(prompt, context, system_prompt)
        
        payload = {
            "model": self._model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": temp,
                "num_predict": tokens,
                "top_p": 0.9,
                "top_k": 40,
                "stop": ["\n\nQUESTION:", "\n\nCONTEXT:"],
            },
        }
        
        try:
            client = await self._get_client()
            
            logger.debug(
                "ollama_request_started",
                model=self._model,
                prompt_length=len(full_prompt),
            )
            
            response = await client.post(
                f"{self._base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            
            data = response.json()
            generated_text = data.get("response", "").strip()
            
            # Ensure slogan is present
            if "Ask. Know. Decide." not in generated_text:
                generated_text += "\n\nAsk. Know. Decide. - One Gambia. One People. One Barrow."
            
            logger.debug(
                "ollama_request_completed",
                response_length=len(generated_text),
            )
            
            return generated_text
            
        except httpx.TimeoutException as e:
            logger.error("ollama_timeout", timeout=self._timeout)
            raise OllamaTimeoutException(self._timeout) from e
            
        except httpx.ConnectError as e:
            logger.error("ollama_connection_error", error=str(e))
            raise OllamaException("Failed to connect to Ollama", e) from e
            
        except httpx.HTTPStatusError as e:
            logger.error("ollama_http_error", status=e.response.status_code)
            raise OllamaException(f"HTTP {e.response.status_code}", e) from e
            
        except Exception as e:
            logger.error("ollama_unexpected_error", error=str(e))
            raise OllamaException(f"Unexpected error: {str(e)}", e) from e
    
    async def generate_with_retry(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_retries: int = 2,
        **kwargs
    ) -> str:
        """
        Generate with retry on failure.
        
        Args:
            prompt: User question
            context: RAG context
            system_prompt: System prompt
            max_retries: Maximum retry attempts
            **kwargs: Additional parameters
            
        Returns:
            Generated response or fallback
        """
        for attempt in range(max_retries + 1):
            try:
                return await self.generate(
                    prompt=prompt,
                    context=context,
                    system_prompt=system_prompt,
                    **kwargs
                )
                
            except OllamaTimeoutException as e:
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(
                        "ollama_retry_timeout",
                        attempt=attempt + 1,
                        wait_seconds=wait_time
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("ollama_max_retries_exceeded")
                    
            except OllamaException as e:
                if attempt < max_retries:
                    wait_time = 1 * (2 ** attempt)
                    logger.warning(
                        "ollama_retry_error",
                        attempt=attempt + 1,
                        error=str(e)
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("ollama_max_retries_exceeded_error")
                    
            except Exception as e:
                logger.error("ollama_unexpected_error_no_retry", error=str(e))
                break
        
        language = kwargs.get("language", "en")
        return self.FALLBACK_MESSAGES.get(language, self.FALLBACK_MESSAGES["en"])
    
    async def is_available(self) -> bool:
        """
        Check if Ollama is available.
        
        Returns:
            True if service is reachable
        """
        try:
            client = await self._get_client()
            response = await client.get(f"{self._base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False
    
    def get_model_name(self) -> str:
        """Get the current model name."""
        return self._model
    
    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "ollama"
    
    async def count_tokens(self, text: str) -> int:
        """
        Estimate token count.
        
        For Llama models, roughly 4 characters per token.
        """
        return len(text) // 4