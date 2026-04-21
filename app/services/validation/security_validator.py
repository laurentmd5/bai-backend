"""
Security validation service for BARROW.AI.
Validates security aspects including rate limiting, IP checks, and attack detection.
"""

import asyncio
import hashlib
import time
from typing import Tuple, Optional, Dict, Any, List
from ipaddress import ip_address, ip_network

from app.core.config import settings
from app.core.logging import get_logger
from app.services.cache.redis_cache import cache_service, CacheNamespace

logger = get_logger(__name__)


class SecurityValidator:
    """
    Comprehensive security validation service.
    
    Handles:
    - Rate limiting with sliding window
    - IP whitelist/blacklist checking
    - Attack pattern detection
    - Request signature validation
    - Suspicious behavior detection
    """
    
    def __init__(self):
        self._admin_ip_whitelist = self._parse_ip_whitelist()
        self._blocked_ips: set = set()
        self._attack_patterns = self._compile_attack_patterns()
    
    def _parse_ip_whitelist(self) -> List[ip_network]:
        """
        Parse admin IP whitelist from settings.
        
        Returns:
            List of IP networks
        """
        whitelist = []
        for ip_str in settings.ADMIN_IP_WHITELIST:
            try:
                whitelist.append(ip_network(ip_str))
            except ValueError as e:
                logger.error("invalid_ip_whitelist_entry", entry=ip_str, error=str(e))
        
        return whitelist
    
    def _compile_attack_patterns(self) -> Dict[str, Any]:
        """
        Compile regex patterns for attack detection.
        
        Returns:
            Dict of compiled patterns
        """
        import re
        
        return {
            "sql_injection": re.compile(
                r"(\bUNION\b.*\bSELECT\b)|(\bDROP\b.*\bTABLE\b)|(--)|(;)|('.*'.*=.*')",
                re.IGNORECASE
            ),
            "path_traversal": re.compile(
                r"\.\./|\.\.\\|%2e%2e%2f|%2e%2e/",
                re.IGNORECASE
            ),
            "command_injection": re.compile(
                r"[;&|`$]|\b(system|exec|passthru|shell_exec)\b",
                re.IGNORECASE
            ),
            "xss": re.compile(
                r"<script|javascript:|on\w+\s*=|alert\s*\(",
                re.IGNORECASE
            ),
        }
    
    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
        identifier: Optional[str] = None,
    ) -> Tuple[bool, int, int]:
        """
        Check if a request is within rate limits.
        
        Uses sliding window algorithm with Redis sorted sets.
        
        Args:
            key: Rate limit key (e.g., "api:chat")
            max_requests: Maximum allowed requests
            window_seconds: Time window in seconds
            identifier: Additional identifier (e.g., IP, session_id)
            
        Returns:
            Tuple of (allowed, remaining, reset_in_seconds)
        """
        full_key = f"rl:{key}"
        if identifier:
            full_key = f"{full_key}:{identifier}"
        
        current_time = time.time()
        window_start = current_time - window_seconds
        
        try:
            # Use Redis sorted set for sliding window
            client = await cache_service._get_client()
            
            # Remove old entries
            await client.zremrangebyscore(full_key, 0, window_start)
            
            # Count current requests
            count = await client.zcard(full_key)
            
            if count >= max_requests:
                # Get oldest request timestamp
                oldest = await client.zrange(full_key, 0, 0, withscores=True)
                if oldest:
                    reset_in = int(oldest[0][1] + window_seconds - current_time)
                    return False, 0, max(1, reset_in)
                return False, 0, window_seconds
            
            # Add current request
            await client.zadd(full_key, {str(current_time): current_time})
            await client.expire(full_key, window_seconds + 1)
            
            remaining = max_requests - count - 1
            
            logger.debug(
                "rate_limit_check_passed",
                key=full_key,
                count=count + 1,
                remaining=remaining
            )
            
            return True, remaining, window_seconds
            
        except Exception as e:
            logger.error("rate_limit_check_failed", error=str(e))
            # Fail open - allow request
            return True, max_requests, window_seconds
    
    async def check_chat_rate_limit(
        self,
        session_id: str,
        ip_address: Optional[str] = None,
    ) -> Tuple[bool, int, int]:
        """
        Check chat endpoint rate limits.
        
        Args:
            session_id: Session identifier
            ip_address: Client IP address
            
        Returns:
            Tuple of (allowed, remaining, reset_in_seconds)
        """
        # Per-session limit
        session_allowed, session_remaining, session_reset = await self.check_rate_limit(
            key="chat:session",
            max_requests=settings.RATE_LIMIT_CHAT_PER_MINUTE,
            window_seconds=60,
            identifier=session_id,
        )
        
        if not session_allowed:
            return False, 0, session_reset
        
        # Per-IP limit (if IP provided)
        if ip_address:
            ip_allowed, ip_remaining, ip_reset = await self.check_rate_limit(
                key="chat:ip",
                max_requests=settings.RATE_LIMIT_CHAT_PER_MINUTE,
                window_seconds=60,
                identifier=ip_address.replace(".", "_"),
            )
            
            if not ip_allowed:
                return False, 0, ip_reset
            
            remaining = min(session_remaining, ip_remaining)
            reset = min(session_reset, ip_reset)
        else:
            remaining = session_remaining
            reset = session_reset
        
        return True, remaining, reset
    
    async def check_admin_rate_limit(
        self,
        admin_id: str,
        ip_address: str,
    ) -> Tuple[bool, int, int]:
        """
        Check admin endpoint rate limits (stricter).
        
        Args:
            admin_id: Admin user ID
            ip_address: Client IP address
            
        Returns:
            Tuple of (allowed, remaining, reset_in_seconds)
        """
        # Per-admin limit
        admin_allowed, admin_remaining, admin_reset = await self.check_rate_limit(
            key="admin:user",
            max_requests=settings.RATE_LIMIT_ADMIN_PER_MINUTE,
            window_seconds=60,
            identifier=admin_id,
        )
        
        if not admin_allowed:
            return False, 0, admin_reset
        
        # Per-IP limit
        ip_allowed, ip_remaining, ip_reset = await self.check_rate_limit(
            key="admin:ip",
            max_requests=settings.RATE_LIMIT_ADMIN_PER_MINUTE,
            window_seconds=60,
            identifier=ip_address.replace(".", "_"),
        )
        
        if not ip_allowed:
            return False, 0, ip_reset
        
        remaining = min(admin_remaining, ip_remaining)
        reset = min(admin_reset, ip_reset)
        
        return True, remaining, reset
    
    async def check_whatsapp_rate_limit(
        self,
        phone_number: str,
    ) -> Tuple[bool, int, int]:
        """
        Check WhatsApp message rate limits.
        
        Args:
            phone_number: User's phone number
            
        Returns:
            Tuple of (allowed, remaining, reset_in_seconds)
        """
        return await self.check_rate_limit(
            key="whatsapp",
            max_requests=settings.RATE_LIMIT_WHATSAPP_PER_MINUTE,
            window_seconds=60,
            identifier=hashlib.sha256(phone_number.encode()).hexdigest()[:16],
        )
    
    async def check_login_rate_limit(
        self,
        ip_address: str,
        email: Optional[str] = None,
    ) -> Tuple[bool, int, int]:
        """
        Check login endpoint rate limits (very strict).
        
        Args:
            ip_address: Client IP address
            email: Attempted email
            
        Returns:
            Tuple of (allowed, remaining, reset_in_seconds)
        """
        # Per-IP limit (strict)
        ip_allowed, ip_remaining, ip_reset = await self.check_rate_limit(
            key="login:ip",
            max_requests=5,  # Very strict - 5 per minute
            window_seconds=60,
            identifier=ip_address.replace(".", "_"),
        )
        
        if not ip_allowed:
            return False, 0, ip_reset
        
        # Per-email limit (if email provided)
        if email:
            email_hash = hashlib.sha256(email.lower().encode()).hexdigest()[:16]
            email_allowed, email_remaining, email_reset = await self.check_rate_limit(
                key="login:email",
                max_requests=10,  # 10 per 5 minutes
                window_seconds=300,
                identifier=email_hash,
            )
            
            if not email_allowed:
                return False, 0, email_reset
            
            remaining = min(ip_remaining, email_remaining)
            reset = min(ip_reset, email_reset)
        else:
            remaining = ip_remaining
            reset = ip_reset
        
        return True, remaining, reset
    
    def is_ip_allowed(self, ip_str: str, is_admin: bool = False) -> bool:
        """
        Check if an IP address is allowed.
        
        Args:
            ip_str: IP address string
            is_admin: Whether this is for admin access
            
        Returns:
            True if allowed
        """
        # Check blacklist first
        if ip_str in self._blocked_ips:
            logger.info("ip_blocked", ip=ip_str)
            return False
        
        # For admin, check whitelist
        if is_admin and self._admin_ip_whitelist:
            try:
                ip = ip_address(ip_str)
                for network in self._admin_ip_whitelist:
                    if ip in network:
                        return True
                
                logger.warning("admin_ip_not_whitelisted", ip=ip_str)
                return False
                
            except ValueError:
                return False
        
        return True
    
    async def block_ip(self, ip_str: str, reason: str, duration_seconds: int = 3600) -> None:
        """
        Block an IP address temporarily.
        
        Args:
            ip_str: IP address to block
            reason: Reason for blocking
            duration_seconds: Block duration
        """
        self._blocked_ips.add(ip_str)
        
        # Store in Redis for persistence across instances
        await cache_service.set(
            CacheNamespace.RATE_LIMIT,
            f"blocked:ip:{ip_str.replace('.', '_')}",
            {"reason": reason, "blocked_at": time.time()},
            ttl=duration_seconds
        )
        
        logger.warning("ip_blocked_temporarily", ip=ip_str, reason=reason, duration=duration_seconds)
    
    async def is_ip_blocked(self, ip_str: str) -> bool:
        """
        Check if an IP is blocked.
        
        Args:
            ip_str: IP address to check
            
        Returns:
            True if blocked
        """
        if ip_str in self._blocked_ips:
            return True
        
        # Check Redis
        blocked = await cache_service.exists(
            CacheNamespace.RATE_LIMIT,
            f"blocked:ip:{ip_str.replace('.', '_')}"
        )
        
        return blocked
    
    def detect_attack_patterns(self, request_data: Dict[str, Any]) -> List[str]:
        """
        Detect attack patterns in request data.
        
        Args:
            request_data: Request data to analyze
            
        Returns:
            List of detected attack types
        """
        detected = []
        
        # Check all string values in request
        def check_value(value: Any) -> None:
            if isinstance(value, str):
                for attack_type, pattern in self._attack_patterns.items():
                    if pattern.search(value):
                        detected.append(attack_type)
            elif isinstance(value, dict):
                for v in value.values():
                    check_value(v)
            elif isinstance(value, list):
                for item in value:
                    check_value(item)
        
        check_value(request_data)
        
        if detected:
            logger.warning(
                "attack_patterns_detected",
                patterns=detected,
                request_preview=str(request_data)[:200]
            )
        
        return detected
    
    async def record_failed_login(
        self,
        ip_address: str,
        email: str,
    ) -> int:
        """
        Record a failed login attempt.
        
        Args:
            ip_address: Client IP
            email: Attempted email
            
        Returns:
            Current failure count
        """
        ip_key = f"failed:ip:{ip_address.replace('.', '_')}"
        email_key = f"failed:email:{hashlib.sha256(email.lower().encode()).hexdigest()[:16]}"
        
        # Increment counters
        ip_count = await cache_service.incr(
            CacheNamespace.LOGIN_FAILURES,
            ip_key,
            amount=1,
            ttl=1800,  # 30 minutes
        )
        
        email_count = await cache_service.incr(
            CacheNamespace.LOGIN_FAILURES,
            email_key,
            amount=1,
            ttl=1800,
        )
        
        # Check if should block IP
        if ip_count >= 10:
            await self.block_ip(ip_address, "excessive_failed_logins", 1800)
        
        logger.warning(
            "failed_login_recorded",
            ip=ip_address,
            email_hash=email_key[:8],
            ip_failures=ip_count,
            email_failures=email_count,
        )
        
        return max(ip_count, email_count)
    
    async def clear_failed_logins(self, ip_address: str, email: str) -> None:
        """
        Clear failed login records after successful login.
        
        Args:
            ip_address: Client IP
            email: User email
        """
        ip_key = f"failed:ip:{ip_address.replace('.', '_')}"
        email_key = f"failed:email:{hashlib.sha256(email.lower().encode()).hexdigest()[:16]}"
        
        await cache_service.delete(CacheNamespace.LOGIN_FAILURES, ip_key)
        await cache_service.delete(CacheNamespace.LOGIN_FAILURES, email_key)
        
        logger.debug("failed_logins_cleared", ip=ip_address)
    
    async def check_suspicious_behavior(
        self,
        session_id: str,
        ip_address: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check for suspicious behavior patterns.
        
        Args:
            session_id: Session identifier
            ip_address: Client IP
            
        Returns:
            Tuple of (is_suspicious, reason)
        """
        # Check request velocity
        velocity_key = f"velocity:{session_id}"
        request_times = await cache_service.get(CacheNamespace.RATE_LIMIT, velocity_key)
        
        if request_times:
            import json
            times = json.loads(request_times) if isinstance(request_times, str) else request_times
            
            if len(times) >= 10:
                # Check if requests are too fast
                if times[-1] - times[0] < 1.0:
                    return True, "request_burst"
                
                # Check if requests are too regular (bot pattern)
                if len(times) >= 5:
                    intervals = [times[i+1] - times[i] for i in range(len(times)-1)]
                    avg_interval = sum(intervals) / len(intervals)
                    variance = sum((i - avg_interval) ** 2 for i in intervals) / len(intervals)
                    
                    if variance < 0.01:
                        return True, "bot_like_pattern"
        
        # Check for rapid IP changes (potential proxy/VPN)
        ip_history_key = f"ip_history:{session_id}"
        ip_history = await cache_service.get(CacheNamespace.RATE_LIMIT, ip_history_key)
        
        if ip_history:
            import json
            ips = json.loads(ip_history) if isinstance(ip_history, str) else ip_history
            
            if len(ips) >= 3 and len(set(ips)) >= 3:
                return True, "rapid_ip_changes"
        
        return False, None
    
    async def record_request_timing(
        self,
        session_id: str,
        ip_address: str,
    ) -> None:
        """
        Record request timing for behavioral analysis.
        
        Args:
            session_id: Session identifier
            ip_address: Client IP
        """
        import json
        
        current_time = time.time()
        
        # Record request time
        velocity_key = f"velocity:{session_id}"
        times = await cache_service.get(CacheNamespace.RATE_LIMIT, velocity_key)
        
        if times:
            times_list = json.loads(times) if isinstance(times, str) else times
        else:
            times_list = []
        
        times_list.append(current_time)
        
        # Keep last 20 requests
        if len(times_list) > 20:
            times_list = times_list[-20:]
        
        await cache_service.set(
            CacheNamespace.RATE_LIMIT,
            velocity_key,
            json.dumps(times_list),
            ttl=300,
        )
        
        # Record IP
        ip_history_key = f"ip_history:{session_id}"
        ips = await cache_service.get(CacheNamespace.RATE_LIMIT, ip_history_key)
        
        if ips:
            ips_list = json.loads(ips) if isinstance(ips, str) else ips
        else:
            ips_list = []
        
        if ip_address not in ips_list:
            ips_list.append(ip_address)
        
        if len(ips_list) > 10:
            ips_list = ips_list[-10:]
        
        await cache_service.set(
            CacheNamespace.RATE_LIMIT,
            ip_history_key,
            json.dumps(ips_list),
            ttl=3600,
        )
    
    def validate_csrf_token(self, token: str, session_id: str) -> bool:
        """
        Validate CSRF token.
        
        Args:
            token: CSRF token from request
            session_id: Session identifier
            
        Returns:
            True if valid
        """
        from app.core.security import verify_csrf_token
        return verify_csrf_token(token, session_id)
    
    def validate_jwt_token(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """
        Validate JWT token.
        
        Args:
            token: JWT token
            token_type: Expected token type
            
        Returns:
            Decoded payload or None if invalid
        """
        from app.core.security import decode_jwt_token
        
        try:
            return decode_jwt_token(token, token_type)
        except Exception as e:
            logger.debug("jwt_validation_failed", error=str(e))
            return None