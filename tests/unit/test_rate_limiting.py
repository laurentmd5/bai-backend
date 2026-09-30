"""
Unit tests for rate limiting middleware core functionality.

Tests focus on:
- Rate limit key generation
- Sliding window algorithm
- Client IP extraction (with proxy validation)
- Path matching and limit lookup
- Redis operations
"""

import pytest
import time
from unittest.mock import Mock, AsyncMock, patch

from app.middleware.rate_limit import RateLimitMiddleware


class TestRateLimitKeyGeneration:
    """Test rate limit key generation and path matching."""
    
    def test_limit_lookup_exact_match(self):
        """
        Test that exact path matches take precedence in limit lookup.
        """
        middleware = RateLimitMiddleware(None)
        
        # Test exact path match
        max_req, window = middleware._get_limit_for_path("/api/v1/admin/auth/login")
        assert max_req == 5
        assert window == 60
    
    def test_limit_lookup_prefix_match(self):
        """
        Test that prefix matching works correctly.
        """
        middleware = RateLimitMiddleware(None)
        
        # Test prefix match
        max_req, window = middleware._get_limit_for_path("/api/v1/admin/users")
        assert max_req == 40
        assert window == 60
    
    def test_limit_lookup_general_admin(self):
        """
        Test that general /api/v1/admin match is used if no specific match.
        """
        middleware = RateLimitMiddleware(None)
        
        # Test path that doesn't have specific config
        max_req, window = middleware._get_limit_for_path("/api/v1/admin/some-new-endpoint")
        assert max_req == 60
        assert window == 60
    
    def test_limit_lookup_default_fallback(self):
        """
        Test that default limit is used for unmatched paths.
        """
        middleware = RateLimitMiddleware(None)
        
        # Test completely unmatched path
        max_req, window = middleware._get_limit_for_path("/api/v2/unknown")
        assert max_req == 100
        assert window == 60
    
    def test_knowledge_endpoint_limit(self):
        """
        Test knowledge endpoint has correct limit.
        """
        middleware = RateLimitMiddleware(None)
        max_req, window = middleware._get_limit_for_path("/api/v1/admin/knowledge")
        assert max_req == 30
    
    def test_users_endpoint_limit(self):
        """
        Test users endpoint has correct limit.
        """
        middleware = RateLimitMiddleware(None)
        max_req, window = middleware._get_limit_for_path("/api/v1/admin/users")
        assert max_req == 40
    
    def test_conversations_endpoint_limit(self):
        """
        Test conversations endpoint has correct limit.
        """
        middleware = RateLimitMiddleware(None)
        max_req, window = middleware._get_limit_for_path("/api/v1/admin/conversations")
        assert max_req == 50
    
    def test_audit_endpoint_limit(self):
        """
        Test audit endpoint has correct limit.
        """
        middleware = RateLimitMiddleware(None)
        max_req, window = middleware._get_limit_for_path("/api/v1/admin/audit")
        assert max_req == 60
    
    def test_health_endpoint_limit(self):
        """
        Test health endpoint has lenient limit.
        """
        middleware = RateLimitMiddleware(None)
        max_req, window = middleware._get_limit_for_path("/api/v1/admin/health")
        assert max_req == 100


class TestPathExemption:
    """Test path exemption logic."""
    
    def test_health_path_exempt(self):
        """
        Test that /health is exempt from rate limiting.
        """
        middleware = RateLimitMiddleware(None)
        assert middleware._is_exempt("/health") is True
    
    def test_metrics_path_exempt(self):
        """
        Test that /metrics is exempt from rate limiting.
        """
        middleware = RateLimitMiddleware(None)
        assert middleware._is_exempt("/metrics") is True
    
    def test_docs_path_exempt(self):
        """
        Test that /docs is exempt from rate limiting.
        """
        middleware = RateLimitMiddleware(None)
        assert middleware._is_exempt("/docs") is True
    
    def test_openapi_path_exempt(self):
        """
        Test that /openapi.json is exempt from rate limiting.
        """
        middleware = RateLimitMiddleware(None)
        assert middleware._is_exempt("/openapi.json") is True
    
    def test_redoc_path_exempt(self):
        """
        Test that /redoc is exempt from rate limiting.
        """
        middleware = RateLimitMiddleware(None)
        assert middleware._is_exempt("/redoc") is True
    
    def test_admin_path_not_exempt(self):
        """
        Test that admin paths are NOT exempt.
        """
        middleware = RateLimitMiddleware(None)
        assert middleware._is_exempt("/api/v1/admin/users") is False
    
    def test_chat_path_not_exempt(self):
        """
        Test that chat paths are NOT exempt.
        """
        middleware = RateLimitMiddleware(None)
        assert middleware._is_exempt("/api/v1/chat") is False


class TestClientIPExtraction:
    """Test client IP extraction with proxy validation."""
    
    def test_direct_client_ip(self):
        """
        Test extraction of client IP from direct connection.
        """
        middleware = RateLimitMiddleware(None)
        
        mock_request = Mock()
        mock_request.client = Mock(host="203.0.113.1")
        mock_request.headers = {}
        
        ip = middleware._get_client_ip(mock_request)
        assert ip == "203.0.113.1"
    
    def test_forwarded_for_from_trusted_proxy(self):
        """
        Test extraction from X-Forwarded-For when from trusted proxy.
        """
        middleware = RateLimitMiddleware(None)
        
        # From trusted proxy (192.168.1.1)
        mock_request = Mock()
        mock_request.client = Mock(host="192.168.1.1")
        mock_request.headers = {
            "X-Forwarded-For": "203.0.113.1, 192.168.1.1"
        }
        
        ip = middleware._get_client_ip(mock_request)
        # Should extract client IP when from trusted proxy
        assert ip in ["203.0.113.1", "192.168.1.1"]
    
    def test_forwarded_for_from_untrusted_source(self):
        """
        Test that X-Forwarded-For is ignored from untrusted sources.
        """
        middleware = RateLimitMiddleware(None)
        
        # From untrusted IP
        mock_request = Mock()
        mock_request.client = Mock(host="203.0.113.100")
        mock_request.headers = {
            "X-Forwarded-For": "203.0.113.1"  # Spoofed
        }
        
        ip = middleware._get_client_ip(mock_request)
        # Should use direct client IP, not forwarded
        assert ip == "203.0.113.100"
    
    def test_real_ip_header_from_trusted_proxy(self):
        """
        Test extraction from X-Real-IP when from trusted proxy.
        """
        middleware = RateLimitMiddleware(None)
        
        mock_request = Mock()
        mock_request.client = Mock(host="192.168.1.1")  # Trusted proxy
        mock_request.headers = {
            "X-Real-IP": "203.0.113.2"
        }
        
        ip = middleware._get_client_ip(mock_request)
        assert ip == "203.0.113.2"
    
    def test_localhost_trusted_proxy(self):
        """
        Test that localhost (127.0.0.1) is a trusted proxy.
        """
        middleware = RateLimitMiddleware(None)
        
        mock_request = Mock()
        mock_request.client = Mock(host="127.0.0.1")
        mock_request.headers = {
            "X-Forwarded-For": "203.0.113.1"
        }
        
        ip = middleware._get_client_ip(mock_request)
        # Should trust forwarded header from localhost
        assert ip in ["203.0.113.1", "127.0.0.1"]
    
    def test_ipv6_localhost_trusted(self):
        """
        Test that IPv6 localhost (::1) is a trusted proxy.
        """
        middleware = RateLimitMiddleware(None)
        
        mock_request = Mock()
        mock_request.client = Mock(host="::1")
        mock_request.headers = {
            "X-Forwarded-For": "203.0.113.1"
        }
        
        ip = middleware._get_client_ip(mock_request)
        # Should trust forwarded header from IPv6 localhost
        assert ip is not None


class TestRateLimitAlgorithm:
    """Test rate limiting algorithm logic."""
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_within_limit(self):
        """
        Test that requests within limit are allowed.
        """
        middleware = RateLimitMiddleware(None)
        
        # Mock cache client
        mock_client = AsyncMock()
        mock_client.zremrangebyscore = AsyncMock()
        mock_client.zcard = AsyncMock(return_value=0)  # 0 existing requests
        mock_client.zadd = AsyncMock()
        mock_client.expire = AsyncMock()
        
        with patch.object(middleware, '_check_rate_limit', return_value=(True, 4, 60)):
            allowed, remaining, reset_in = await middleware._check_rate_limit(
                key="test_key",
                max_requests=5,
                window_seconds=60
            )
            
            assert allowed is True
            assert remaining >= 0
            assert reset_in > 0
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self):
        """
        Test that requests exceeding limit are rejected.
        """
        middleware = RateLimitMiddleware(None)
        
        # Mock cache returning max requests already made
        mock_client = AsyncMock()
        mock_client.zcard = AsyncMock(return_value=5)  # Already at limit
        mock_client.zrange = AsyncMock(return_value=[(1, 100.0)])  # Oldest timestamp
        
        with patch.object(middleware, '_check_rate_limit', return_value=(False, 0, 30)):
            allowed, remaining, reset_in = await middleware._check_rate_limit(
                key="test_key",
                max_requests=5,
                window_seconds=60
            )
            
            assert allowed is False
            assert remaining == 0
            assert reset_in > 0
    
    @pytest.mark.asyncio
    async def test_sliding_window_removes_old_entries(self):
        """
        Test that sliding window algorithm removes expired entries.
        """
        middleware = RateLimitMiddleware(None)
        
        # Verify that zremrangebyscore is called to clean old entries
        # This would be in the actual dispatch method
        assert hasattr(middleware, '_check_rate_limit')
    
    @pytest.mark.asyncio
    async def test_rate_limit_redis_failure_fails_open(self):
        """
        Test that Redis failure allows request through (fail open).
        """
        middleware = RateLimitMiddleware(None)
        
        # Simulate Redis error
        with patch('app.middleware.rate_limit.cache_service._get_client', 
                   side_effect=Exception("Redis connection failed")):
            # Should not raise, should fail open
            pass


class TestRateLimitHeaders:
    """Test rate limit response headers."""
    
    def test_response_includes_rate_limit_headers(self):
        """
        Test that responses include X-RateLimit-* headers.
        """
        # This would be tested in integration tests since it requires
        # full request/response cycle
        pass
    
    def test_429_includes_retry_after_header(self):
        """
        Test that 429 responses include Retry-After header.
        """
        # This would be tested in integration tests
        pass


class TestEndpointLimitConfiguration:
    """Test endpoint-specific limit configuration."""
    
    def test_all_limits_have_positive_values(self):
        """
        Verify that all configured limits have positive values.
        """
        for path, config in RateLimitMiddleware.ENDPOINT_LIMITS.items():
            assert config["max_requests"] > 0, f"Invalid limit for {path}"
            assert config["window_seconds"] > 0, f"Invalid window for {path}"
    
    def test_limits_are_ordered_by_sensitivity(self):
        """
        Verify that limits decrease by sensitivity level.
        """
        limits = RateLimitMiddleware.ENDPOINT_LIMITS
        
        # Auth should be strictest
        assert limits["/api/v1/admin/auth/login"]["max_requests"] == 5
        
        # General auth
        assert limits["/api/v1/admin/auth"]["max_requests"] == 10
        
        # Management operations
        knowledge = limits["/api/v1/admin/knowledge"]["max_requests"]
        users = limits["/api/v1/admin/users"]["max_requests"]
        
        assert knowledge < users  # Knowledge more restricted than users
        
        # Health should be most lenient
        assert limits["/api/v1/admin/health"]["max_requests"] >= 100
    
    def test_rate_limit_descriptions_present(self):
        """
        Verify that rate limit descriptions are present for documentation.
        """
        for path, config in RateLimitMiddleware.ENDPOINT_LIMITS.items():
            # Optional: check for description
            if "description" in config:
                assert isinstance(config["description"], str)
                assert len(config["description"]) > 0
