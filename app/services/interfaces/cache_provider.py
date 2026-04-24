"""
Cache provider interface for BARROW.AI.
Defines the abstract base class for cache implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class ICacheProvider(ABC):
    """Abstract interface for cache providers."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Set value in cache with TTL."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete value from cache."""
        pass
    
    @abstractmethod
    async def clear(self) -> None:
        """Clear all cache."""
        pass
