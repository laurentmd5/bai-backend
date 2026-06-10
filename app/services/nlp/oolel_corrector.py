import httpx
import asyncio
import json
from typing import Optional, Tuple
from datetime import datetime
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

class OolelCorrector:
    """
    Service for normalizing informal Wolof text using Oolel-Corrector via Hugging Face Inference API.
    """
    
    def __init__(self):
        self.endpoint = settings.OOLEL_CORRECTOR_ENDPOINT
        self.api_key = settings.HF_API_KEY.get_secret_value() if settings.HF_API_KEY else None
        
        self.headers = {
            "Content-Type": "application/json"
        }
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"
            
    async def is_available(self) -> bool:
        """Check if the API is configured and reachable."""
        return self.api_key is not None

    async def normalize_text(self, text: str, max_retries: int = 3) -> str:
        """
        Normalize informal Wolof text.
        
        Args:
            text: Raw input text
            max_retries: Maximum number of retries (handles 503 Model Loading)
            
        Returns:
            Normalized text (or original text if it fails)
        """
        if not self.api_key or not text.strip():
            return text
            
        payload = {
            "inputs": text,
            "parameters": {
                "max_new_tokens": 512,
                "temperature": 0.1,
                "return_full_text": False
            }
        }
        
        last_error = None
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(max_retries):
                try:
                    response = await client.post(
                        self.endpoint,
                        headers=self.headers,
                        json=payload
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        if isinstance(data, list) and len(data) > 0 and "generated_text" in data[0]:
                            normalized = data[0]["generated_text"].strip()
                            logger.debug("oolel_corrector_success", original=text, normalized=normalized)
                            return normalized
                        return text
                        
                    elif response.status_code == 503:
                        # Model is loading
                        try:
                            data = response.json()
                            estimated_time = data.get("estimated_time", 10.0)
                        except:
                            estimated_time = 10.0
                            
                        logger.warning("oolel_corrector_loading", estimated_time=estimated_time, attempt=attempt+1)
                        # Wait for the model to load before retrying
                        await asyncio.sleep(min(estimated_time, 20.0))
                        
                    elif response.status_code == 429:
                        wait_time = 2 ** attempt
                        logger.warning("oolel_corrector_rate_limit", wait_seconds=wait_time, attempt=attempt+1)
                        await asyncio.sleep(wait_time)
                        
                    else:
                        logger.error("oolel_corrector_error", status_code=response.status_code, body=response.text)
                        # If it's a 4xx (other than 429) or 5xx error, just fallback to original text
                        break
                        
                except httpx.RequestError as e:
                    last_error = e
                    wait_time = 2 ** attempt
                    logger.warning("oolel_corrector_request_error", error=str(e), wait_seconds=wait_time, attempt=attempt+1)
                    await asyncio.sleep(wait_time)
                    
        logger.error("oolel_corrector_failed_all_retries", last_error=str(last_error))
        return text

# Singleton instance
oolel_corrector = OolelCorrector()
