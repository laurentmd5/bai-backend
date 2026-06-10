"""
Redis cache service for BARROW.AI.
Provides comprehensive caching strategies for RAG responses, embeddings, sessions, and rate limiting.
Implements cache stampede prevention, TTL management, and serialization.
"""

import hashlib
import json
import asyncio
from typing import Optional, Any, Dict, List, Set, Tuple, Union
from datetime import timedelta
from enum import Enum

from redis.asyncio import Redis

from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.redis_client import get_redis, execute_redis_operation, RedisException
from app.core.logging import get_logger

logger = get_logger(__name__)


class CacheNamespace(str, Enum):
    """Cache key namespaces for logical separation."""
    RAG_RESPONSE = "rag:response"
    RAG_EMBEDDING = "rag:embedding"
    SESSION = "session"
    CHAT_SESSION = "chat:session"
    RATE_LIMIT = "rl"
    WHATSAPP_OPTOUT = "wa:optout"
    WHATSAPP_PROCESSED = "wa:processed"
    JWT_BLACKLIST = "blacklist"
    TWO_FACTOR_SESSION = "2fa:session"
    LOGIN_FAILURES = "login:failures"
    ADMIN_SESSION = "admin:session"
    CSRF_TOKEN = "csrf"
    LOCK = "lock"


class RedisCacheService:
    """
    Comprehensive Redis caching service.
    Handles all cache operations with proper serialization and error handling.
    """
    
    def __init__(self):
        self._client: Optional[Redis] = None
        self._default_ttl = settings.CACHE_RAG_TTL_SECONDS
    
    async def _get_client(self) -> Redis:
        """Lazy-load Redis client."""
        if not self._client:
            self._client = await get_redis()
        return self._client
    
    async def is_connected(self) -> bool:
        """Check if Redis is reachable."""
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except Exception:
            return False
    
    def _make_key(self, namespace: CacheNamespace, *parts: str) -> str:
        """
        Create a namespaced cache key.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            
        Returns:
            str: Full cache key
        """
        return f"{namespace.value}:{':'.join(parts)}"
    
    def _serialize(self, value: Any) -> str:
        """
        Serialize value for Redis storage.
        
        Args:
            value: Value to serialize
            
        Returns:
            str: JSON string
        """
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=str)
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, default=str)
    
    def _deserialize(self, value: Optional[str]) -> Any:
        """
        Deserialize value from Redis.
        
        Args:
            value: String value from Redis
            
        Returns:
            Any: Deserialized value or None
        """
        if value is None:
            return None
        
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    
    # =========================================================================
    # Basic Operations
    # =========================================================================
    
    async def get(self, namespace: CacheNamespace, *parts: str) -> Optional[Any]:
        """
        Get a value from cache.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            
        Returns:
            Cached value or None
        """
        key = self._make_key(namespace, *parts)
        
        async def _get(client: Redis):
            value = await client.get(key)
            return self._deserialize(value)
        
        return await execute_redis_operation(
            f"get:{key}",
            _get,
            fallback_value=None
        )
    
    async def set(
        self,
        namespace: CacheNamespace,
        *parts: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set a value in cache.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            value: Value to cache
            ttl: TTL in seconds (uses default if None)
            
        Returns:
            bool: True if successful
        """
        key = self._make_key(namespace, *parts)
        ttl = ttl if ttl is not None else self._default_ttl
        serialized = self._serialize(value)
        
        async def _set(client: Redis):
            await client.setex(key, ttl, serialized)
            return True
        
        result = await execute_redis_operation(
            f"set:{key}",
            _set,
            fallback_value=False
        )
        return result is True
    
    async def delete(self, namespace: CacheNamespace, *parts: str) -> int:
        """
        Delete a key from cache.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            
        Returns:
            int: Number of keys deleted
        """
        key = self._make_key(namespace, *parts)
        
        async def _delete(client: Redis):
            return await client.delete(key)
        
        result = await execute_redis_operation(
            f"delete:{key}",
            _delete,
            fallback_value=0
        )
        return result if isinstance(result, int) else 0
    
    async def exists(self, namespace: CacheNamespace, *parts: str) -> bool:
        """
        Check if a key exists in cache.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            
        Returns:
            bool: True if key exists
        """
        key = self._make_key(namespace, *parts)
        
        async def _exists(client: Redis):
            return await client.exists(key) > 0
        
        result = await execute_redis_operation(
            f"exists:{key}",
            _exists,
            fallback_value=False
        )
        return result is True
    
    async def expire(self, namespace: CacheNamespace, *parts: str, ttl: int) -> bool:
        """
        Set TTL for an existing key.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            ttl: TTL in seconds
            
        Returns:
            bool: True if successful
        """
        key = self._make_key(namespace, *parts)
        
        async def _expire(client: Redis):
            return await client.expire(key, ttl)
        
        result = await execute_redis_operation(
            f"expire:{key}",
            _expire,
            fallback_value=False
        )
        return result is True
    
    async def ttl(self, namespace: CacheNamespace, *parts: str) -> int:
        """
        Get remaining TTL for a key.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            
        Returns:
            int: Remaining TTL in seconds, -1 if no TTL, -2 if key doesn't exist
        """
        key = self._make_key(namespace, *parts)
        
        async def _ttl(client: Redis):
            return await client.ttl(key)
        
        result = await execute_redis_operation(
            f"ttl:{key}",
            _ttl,
            fallback_value=-2
        )
        return result if isinstance(result, int) else -2
    
    # =========================================================================
    # Increment/Decrement Operations
    # =========================================================================
    
    async def incr(
        self,
        namespace: CacheNamespace,
        *parts: str,
        amount: int = 1,
        ttl: Optional[int] = None
    ) -> int:
        """
        Increment a counter.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            amount: Amount to increment by
            ttl: Optional TTL to set on first increment
            
        Returns:
            int: New counter value
        """
        key = self._make_key(namespace, *parts)
        
        async def _incr(client: Redis):
            value = await client.incrby(key, amount)
            if ttl and value == amount:
                await client.expire(key, ttl)
            return value
        
        result = await execute_redis_operation(
            f"incr:{key}",
            _incr,
            fallback_value=0
        )
        return result if isinstance(result, int) else 0
    
    async def decr(
        self,
        namespace: CacheNamespace,
        *parts: str,
        amount: int = 1
    ) -> int:
        """
        Decrement a counter.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            amount: Amount to decrement by
            
        Returns:
            int: New counter value
        """
        key = self._make_key(namespace, *parts)
        
        async def _decr(client: Redis):
            return await client.decrby(key, amount)
        
        result = await execute_redis_operation(
            f"decr:{key}",
            _decr,
            fallback_value=0
        )
        return result if isinstance(result, int) else 0
    
    # =========================================================================
    # Hash Operations
    # =========================================================================
    
    async def hset(
        self,
        namespace: CacheNamespace,
        *parts: str,
        mapping: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> int:
        """
        Set hash field values.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            mapping: Dict of field-value pairs
            ttl: Optional TTL
            
        Returns:
            int: Number of fields added
        """
        key = self._make_key(namespace, *parts)
        serialized = {k: self._serialize(v) for k, v in mapping.items()}
        
        async def _hset(client: Redis):
            result = await client.hset(key, mapping=serialized)
            if ttl:
                await client.expire(key, ttl)
            return result
        
        result = await execute_redis_operation(
            f"hset:{key}",
            _hset,
            fallback_value=0
        )
        return result if isinstance(result, int) else 0
    
    async def hget(
        self,
        namespace: CacheNamespace,
        *parts: str,
        field: str
    ) -> Optional[Any]:
        """
        Get hash field value.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            field: Field name
            
        Returns:
            Field value or None
        """
        key = self._make_key(namespace, *parts)
        
        async def _hget(client: Redis):
            value = await client.hget(key, field)
            return self._deserialize(value)
        
        return await execute_redis_operation(
            f"hget:{key}:{field}",
            _hget,
            fallback_value=None
        )
    
    async def hgetall(
        self,
        namespace: CacheNamespace,
        *parts: str
    ) -> Dict[str, Any]:
        """
        Get all hash fields and values.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            
        Returns:
            Dict of field-value pairs
        """
        key = self._make_key(namespace, *parts)
        
        async def _hgetall(client: Redis):
            data = await client.hgetall(key)
            return {k: self._deserialize(v) for k, v in data.items()}
        
        result = await execute_redis_operation(
            f"hgetall:{key}",
            _hgetall,
            fallback_value={}
        )
        return result if isinstance(result, dict) else {}
    
    async def hdel(
        self,
        namespace: CacheNamespace,
        parts: tuple[str, ...],
        fields: tuple[str, ...]
    ) -> int:
        """
        Delete hash fields.
        
        Args:
            namespace: Cache namespace
            parts: Key components tuple
            fields: Fields to delete tuple
            
        Returns:
            int: Number of fields deleted
        """
        if not fields:
            return 0
        
        key = self._make_key(namespace, *parts)
        
        async def _hdel(client: Redis):
            return await client.hdel(key, *fields)
        
        result = await execute_redis_operation(
            f"hdel:{key}",
            _hdel,
            fallback_value=0
        )
        return result if isinstance(result, int) else 0
    
    # =========================================================================
    # Set Operations
    # =========================================================================
    
    async def sadd(
        self,
        namespace: CacheNamespace,
        parts: tuple[str, ...],
        members: tuple[str, ...]
    ) -> int:
        """
        Add members to a set.
        
        Args:
            namespace: Cache namespace
            parts: Key components tuple
            members: Members to add tuple
            
        Returns:
            int: Number of members added
        """
        if not members:
            return 0
        
        key = self._make_key(namespace, *parts)
        
        async def _sadd(client: Redis):
            return await client.sadd(key, *members)
        
        result = await execute_redis_operation(
            f"sadd:{key}",
            _sadd,
            fallback_value=0
        )
        return result if isinstance(result, int) else 0
    
    async def sismember(
        self,
        namespace: CacheNamespace,
        *parts: str,
        member: str
    ) -> bool:
        """
        Check if member exists in set.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            member: Member to check
            
        Returns:
            bool: True if member exists
        """
        key = self._make_key(namespace, *parts)
        
        async def _sismember(client: Redis):
            return await client.sismember(key, member)
        
        result = await execute_redis_operation(
            f"sismember:{key}",
            _sismember,
            fallback_value=False
        )
        return result is True
    
    async def srem(
        self,
        namespace: CacheNamespace,
        parts: tuple[str, ...],
        members: tuple[str, ...]
    ) -> int:
        """
        Remove members from a set.
        
        Args:
            namespace: Cache namespace
            parts: Key components tuple
            *members: Members to remove
            
        Returns:
            int: Number of members removed
        """
        if not members:
            return 0
        
        key = self._make_key(namespace, *parts)
        
        async def _srem(client: Redis):
            return await client.srem(key, *members)
        
        result = await execute_redis_operation(
            f"srem:{key}",
            _srem,
            fallback_value=0
        )
        return result if isinstance(result, int) else 0
    
    async def smembers(
        self,
        namespace: CacheNamespace,
        *parts: str
    ) -> Set[str]:
        """
        Get all members of a set.
        
        Args:
            namespace: Cache namespace
            *parts: Key components
            
        Returns:
            Set[str]: All set members
        """
        key = self._make_key(namespace, *parts)
        
        async def _smembers(client: Redis):
            return await client.smembers(key)
        
        result = await execute_redis_operation(
            f"smembers:{key}",
            _smembers,
            fallback_value=set()
        )
        return result if isinstance(result, set) else set()
    
    # =========================================================================
    # Specialized Caching Methods
    # =========================================================================
    
    def _hash_question(self, question: str) -> str:
        """
        Create a deterministic hash for a question.
        Normalizes input for better cache hit rate.
        
        Args:
            question: User question
            
        Returns:
            str: SHA-256 hash
        """
        normalized = question.lower().strip()
        normalized = ''.join(c for c in normalized if c.isalnum() or c.isspace())
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    async def get_rag_response(self, question: str) -> Optional[Dict[str, Any]]:
        """
        Get cached RAG response for a question.
        
        Args:
            question: User question
            
        Returns:
            Cached response dict or None
        """
        question_hash = self._hash_question(question)
        return await self.get(CacheNamespace.RAG_RESPONSE, question_hash)
    
    async def set_rag_response(
        self,
        question: str,
        response: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache RAG response for a question.
        
        Args:
            question: User question
            response: Response dict to cache
            ttl: Optional TTL override
            
        Returns:
            bool: True if successful
        """
        ttl = ttl or settings.CACHE_RAG_TTL_SECONDS
        question_hash = self._hash_question(question)
        return await self.set(
            CacheNamespace.RAG_RESPONSE,
            question_hash,
            value=response,
            ttl=ttl
        )
    
    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Get cached embedding for text.
        
        Args:
            text: Text to get embedding for
            
        Returns:
            List[float] or None
        """
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        return await self.get(CacheNamespace.RAG_EMBEDDING, text_hash)
    
    async def set_embedding(
        self,
        text: str,
        embedding: List[float],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache embedding for text.
        
        Args:
            text: Original text
            embedding: Embedding vector
            ttl: Optional TTL override
            
        Returns:
            bool: True if successful
        """
        ttl = ttl or settings.CACHE_EMBEDDING_TTL_SECONDS
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        return await self.set(
            CacheNamespace.RAG_EMBEDDING,
            text_hash,
            value=embedding,
            ttl=ttl
        )
    
    # =========================================================================
    # Session Management
    # =========================================================================
    
    async def create_chat_session(
        self,
        session_id: str,
        language: str = "en",
        channel: str = "web"
    ) -> bool:
        """
        Create a new chat session.
        
        Args:
            session_id: Unique session ID
            language: User's language
            channel: 'web' or 'whatsapp'
            
        Returns:
            bool: True if successful
        """
        import time
        
        return await self.hset(
            CacheNamespace.CHAT_SESSION,
            session_id,
            mapping={
                "language": language,
                "channel": channel,
                "message_count": "0",
                "created_at": str(time.time()),
                "last_active": str(time.time()),
            },
            ttl=settings.CACHE_SESSION_TTL_SECONDS
        )
    
    async def update_chat_session_activity(self, session_id: str) -> bool:
        """
        Update last_active and increment message count.
        
        Args:
            session_id: Session ID
            
        Returns:
            bool: True if successful
        """
        import time
        
        key = self._make_key(CacheNamespace.CHAT_SESSION, session_id)
        
        async def _update(client: Redis):
            exists = await client.exists(key)
            if not exists:
                return False
            
            await client.hincrby(key, "message_count", 1)
            await client.hset(key, "last_active", str(time.time()))
            return True
        
        result = await execute_redis_operation(
            f"update_session:{session_id}",
            _update,
            fallback_value=False
        )
        return result is True
    
    async def get_chat_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get chat session data.
        
        Args:
            session_id: Session ID
            
        Returns:
            Session dict or None
        """
        return await self.hgetall(CacheNamespace.CHAT_SESSION, session_id)
    
    # =========================================================================
    # Rate Limiting
    # =========================================================================
    
    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> Tuple[bool, int, int]:
        """
        Check if request is within rate limit using sliding window.
        
        Args:
            key: Unique key (e.g., IP + endpoint)
            max_requests: Maximum allowed requests
            window_seconds: Time window in seconds
            
        Returns:
            Tuple[bool, int, int]: (allowed, remaining, reset_in_seconds)
        """
        import time
        
        current_time = time.time()
        window_start = current_time - window_seconds
        
        async def _check(client: Redis):
            # Remove old entries
            await client.zremrangebyscore(key, 0, window_start)
            
            # Count requests in window
            count = await client.zcard(key)
            
            if count >= max_requests:
                # Get oldest request to calculate reset time
                oldest = await client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    reset_in = int(oldest[0][1] + window_seconds - current_time)
                    return False, 0, max(1, reset_in)
                return False, 0, window_seconds
            
            # Add current request
            await client.zadd(key, {str(current_time): current_time})
            await client.expire(key, window_seconds)
            
            remaining = max_requests - count - 1
            return True, remaining, window_seconds
        
        result = await execute_redis_operation(
            f"rate_limit:{key}",
            _check,
            fallback_value=(True, max_requests, window_seconds)  # Fail open
        )
        
        if isinstance(result, tuple) and len(result) == 3:
            return result
        return True, max_requests, window_seconds
    
    # =========================================================================
    # WhatsApp Opt-Out Management
    # =========================================================================
    
    async def add_opt_out(self, phone_number: str) -> bool:
        """
        Add phone number to opt-out set.
        
        Args:
            phone_number: E.164 formatted phone number
            
        Returns:
            bool: True if added
        """
        result = await self.sadd(
            CacheNamespace.WHATSAPP_OPTOUT,
            parts=(),
            members=(phone_number,)
        )
        return result > 0
    
    async def is_opted_out(self, phone_number: str) -> bool:
        """
        Check if phone number is opted out.
        
        Args:
            phone_number: E.164 formatted phone number
            
        Returns:
            bool: True if opted out
        """
        return await self.sismember(
            CacheNamespace.WHATSAPP_OPTOUT,
            member=phone_number
        )
    
    async def remove_opt_out(self, phone_number: str) -> bool:
        """
        Remove phone number from opt-out set.
        
        Args:
            phone_number: E.164 formatted phone number
            
        Returns:
            bool: True if removed
        """
        result = await self.srem(
            CacheNamespace.WHATSAPP_OPTOUT,
            parts=(),
            members=(phone_number,)
        )
        return result > 0
    
    async def mark_whatsapp_processed(self, message_id: str, ttl: int = 3600) -> bool:
        """
        Mark WhatsApp message as processed for idempotency.
        
        Args:
            message_id: WhatsApp message ID
            ttl: TTL in seconds (default 1 hour)
            
        Returns:
            bool: True if marked
        """
        return await self.set(
            CacheNamespace.WHATSAPP_PROCESSED,
            message_id,
            value="1",
            ttl=ttl
        )
    
    async def is_whatsapp_processed(self, message_id: str) -> bool:
        """
        Check if WhatsApp message was already processed.
        
        Args:
            message_id: WhatsApp message ID
            
        Returns:
            bool: True if already processed
        """
        return await self.exists(CacheNamespace.WHATSAPP_PROCESSED, message_id)
    
    # =========================================================================
    # Audio Transcript Caching
    # =========================================================================
    
    async def get_audio_transcript(self, audio_hash: str) -> Optional[str]:
        """
        Get cached transcript for an audio hash.
        
        Args:
            audio_hash: Hash of the audio file
            
        Returns:
            Cached transcript or None
        """
        return await self.get(CacheNamespace.RAG_RESPONSE, f"audio:transcript:{audio_hash}")
    
    async def set_audio_transcript(self, audio_hash: str, transcript: str, ttl: int) -> bool:
        """
        Cache a transcribed audio.
        
        Args:
            audio_hash: Hash of the audio file
            transcript: Transcribed text
            ttl: Time to live in seconds
            
        Returns:
            bool: True if successful
        """
        return await self.set(
            CacheNamespace.RAG_RESPONSE,
            f"audio:transcript:{audio_hash}",
            value=transcript,
            ttl=ttl
        )
    
    # =========================================================================
    # JWT Blacklist
    # =========================================================================
    
    async def blacklist_token(self, jti: str, ttl: int) -> bool:
        """
        Add JWT to blacklist.
        
        Args:
            jti: JWT ID
            ttl: Time until token expires
            
        Returns:
            bool: True if blacklisted
        """
        return await self.set(
            CacheNamespace.JWT_BLACKLIST,
            jti,
            value="1",
            ttl=ttl
        )
    
    async def is_token_blacklisted(self, jti: str) -> bool:
        """
        Check if JWT is blacklisted.
        
        Args:
            jti: JWT ID
            
        Returns:
            bool: True if blacklisted
        """
        return await self.exists(CacheNamespace.JWT_BLACKLIST, jti)
    
    # =========================================================================
    # Distributed Locks
    # =========================================================================
    
    @asynccontextmanager
    async def lock(
        self,
        resource: str,
        ttl: int = 30,
        retry_times: int = 3,
        retry_delay: float = 0.1
    ):
        """
        Distributed lock context manager.
        
        Args:
            resource: Resource name to lock
            ttl: Lock TTL in seconds
            retry_times: Number of acquisition retries
            retry_delay: Delay between retries
            
        Yields:
            bool: True if lock acquired, False otherwise
        """
        lock_key = self._make_key(CacheNamespace.LOCK, resource)
        lock_value = str(asyncio.get_event_loop().time())
        acquired = False
        
        for attempt in range(retry_times):
            try:
                client = await self._get_client()
                # Use SET NX with TTL for atomic lock acquisition
                acquired = await client.set(
                    lock_key,
                    lock_value,
                    nx=True,
                    ex=ttl
                )
                if acquired:
                    break
                await asyncio.sleep(retry_delay * (2 ** attempt))
            except Exception as e:
                logger.warning(
                    "lock_acquisition_failed",
                    resource=resource,
                    attempt=attempt + 1,
                    error=str(e)
                )
        
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    client = await self._get_client()
                    # Only release if we still hold the lock
                    current = await client.get(lock_key)
                    if current == lock_value:
                        await client.delete(lock_key)
                except Exception as e:
                    logger.warning(
                        "lock_release_failed",
                        resource=resource,
                        error=str(e)
                    )
    
    # =========================================================================
    # Cache Invalidation and Maintenance
    # =========================================================================
    
    async def invalidate_rag_cache(self) -> int:
        """
        Invalidate all RAG response cache entries.
        Used when knowledge base is updated.
        
        Returns:
            int: Number of keys deleted
        """
        pattern = f"{CacheNamespace.RAG_RESPONSE.value}:*"
        
        async def _delete_pattern(client: Redis):
            deleted = 0
            cursor = 0
            while True:
                cursor, keys = await client.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100
                )
                if keys:
                    deleted += await client.delete(*keys)
                if cursor == 0:
                    break
            return deleted
        
        result = await execute_redis_operation(
            "invalidate_rag_cache",
            _delete_pattern,
            fallback_value=0
        )
        logger.info("rag_cache_invalidated", keys_deleted=result)
        return result if isinstance(result, int) else 0
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics for monitoring.
        
        Returns:
            Dict with cache metrics
        """
        try:
            client = await self._get_client()
            info = await client.info("stats")
            memory = await client.info("memory")
            
            return {
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0)
                ),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "total_connections_received": info.get("total_connections_received", 0),
                "used_memory_human": memory.get("used_memory_human", "0"),
                "connected_clients": info.get("connected_clients", 0),
                "evicted_keys": info.get("evicted_keys", 0),
                "expired_keys": info.get("expired_keys", 0),
            }
        except Exception as e:
            logger.error("cache_stats_failed", error=str(e))
            return {"error": str(e)}
    
    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """Calculate cache hit rate."""
        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)


# Global cache service instance
cache_service = RedisCacheService()