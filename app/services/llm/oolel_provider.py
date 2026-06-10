import asyncio
import json
from typing import Optional, List, Dict, Any
import httpx

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


class OolelProvider(ILLMProvider):
    """
    Oolel LLM Provider implementation for BARROW.AI using Hugging Face Inference API.
    Designed for Wolof translation and generation tasks.
    """
    
    def __init__(self):
        self.endpoint = settings.OOLEL_LLM_ENDPOINT
        self.api_key = settings.HF_API_KEY.get_secret_value() if settings.HF_API_KEY else None
        
        self.headers = {
            "Content-Type": "application/json"
        }
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"
            
        logger.info(f"OolelProvider initialized with endpoint: {self.endpoint}")

    async def generate(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        language: str = "wolof",
    ) -> str:
        """
        Generate a response using Oolel via Hugging Face Inference API.
        """
        if not self.api_key:
            raise LLMUnavailableException("Hugging Face API key not configured for Oolel.")
            
        # Build the prompt
        # Oolel is based on Qwen 2.5, which uses ChatML format usually, but HF API might expect raw text or chat format.
        # We'll construct a simple prompt combining system prompt and user prompt.
        full_prompt = ""
        if system_prompt:
            full_prompt += f"System: {system_prompt}\n\n"
        if context:
            full_prompt += f"Context: {context}\n\n"
        
        full_prompt += f"User: {prompt}\nAssistant:"
        
        payload = {
            "inputs": full_prompt,
            "parameters": {
                "max_new_tokens": max_tokens or 512,
                "temperature": temperature or 0.3,
                "return_full_text": False
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.endpoint,
                    headers=self.headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0 and "generated_text" in data[0]:
                        return data[0]["generated_text"].strip()
                    raise LLMException(f"Unexpected response format from Oolel: {data}")
                    
                elif response.status_code == 503:
                    raise LLMUnavailableException(f"Oolel model is loading or unavailable: {response.text}")
                elif response.status_code == 429:
                    raise LLMException("Hugging Face API rate limit exceeded.", status_code=429)
                else:
                    raise LLMException(f"Oolel API error: {response.status_code} - {response.text}")
                    
        except httpx.TimeoutException as e:
            logger.error("oolel_timeout", error=str(e))
            raise LLMTimeoutException("Oolel API request timed out") from e
        except httpx.RequestError as e:
            logger.error("oolel_request_error", error=str(e))
            raise LLMException(f"Error communicating with Oolel API: {str(e)}") from e

    async def generate_with_retry(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_retries: int = 3,
        **kwargs
    ) -> str:
        """Generate with automatic retry on transient failures (like 503 Model Loading)."""
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                return await self.generate(
                    prompt=prompt,
                    context=context,
                    system_prompt=system_prompt,
                    **kwargs
                )
                
            except LLMTimeoutException as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning("oolel_retry_timeout", attempt=attempt + 1, wait_seconds=wait_time)
                    await asyncio.sleep(wait_time)
                    
            except LLMUnavailableException as e:
                # 503 Model Loading is common on HF free tier
                last_error = e
                if attempt < max_retries:
                    wait_time = 5 * (attempt + 1)
                    logger.warning("oolel_retry_loading", attempt=attempt + 1, wait_seconds=wait_time)
                    await asyncio.sleep(wait_time)
                    
            except LLMException as e:
                last_error = e
                if "429" in str(e) and attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning("oolel_retry_rate_limit", attempt=attempt + 1, wait_seconds=wait_time)
                    await asyncio.sleep(wait_time)
                else:
                    raise e
                    
        logger.error("oolel_max_retries_exceeded")
        raise last_error

    async def is_available(self) -> bool:
        return self.api_key is not None

    def get_model_name(self) -> str:
        return "oolel-v0.1-7b"

    def get_provider_name(self) -> str:
        return "Oolel"
