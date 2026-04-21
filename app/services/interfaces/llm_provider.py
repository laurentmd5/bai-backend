"""
LLM Provider interface for BARROW.AI.
Defines abstract base class for language model providers.
Enables dependency inversion for easy swapping between Gemini and Ollama.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class ILLMProvider(ABC):
    """
    Abstract interface for Language Model providers.
    
    This interface allows the application to switch between different
    LLM implementations (Gemini, Ollama, etc.) without changing business logic.
    
    SOLID Principle: Dependency Inversion
    - High-level modules (ChatService) depend on this abstraction
    - Low-level modules (GeminiProvider, OllamaProvider) implement this abstraction
    """
    
    @abstractmethod
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
        Generate a response from the language model.
        
        Args:
            prompt: The user's question or input
            context: Additional context (e.g., RAG chunks) to ground the response
            system_prompt: System instructions to control behavior
            temperature: Sampling temperature (0.0 to 1.0) - lower is more deterministic
            max_tokens: Maximum number of tokens to generate
            language: Target language for response ('en', 'fr', 'mandinka', 'wolof')
            
        Returns:
            Generated text response
            
        Raises:
            LLMException: If generation fails
            LLMTimeoutException: If request times out
            LLMUnavailableException: If service is unavailable
        """
        pass
    
    @abstractmethod
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
        
        Args:
            prompt: The user's question
            context: RAG context
            system_prompt: System instructions
            max_retries: Maximum number of retry attempts
            **kwargs: Additional generation parameters
            
        Returns:
            Generated text response
        """
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if the LLM provider is available and healthy.
        
        Returns:
            True if the service is reachable and responding
        """
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """
        Get the name of the current model being used.
        
        Returns:
            Model identifier string
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Get the name of the provider.
        
        Returns:
            Provider name (e.g., 'gemini', 'ollama')
        """
        pass
    
    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in the given text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Estimated token count
        """
        pass