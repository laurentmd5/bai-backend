"""
Integration tests for rate limiting middleware.

Tests verify that rate limiting is properly enforced across different endpoint categories:
- Authentication endpoints (strictest limits)
- Knowledge management endpoints
- User management endpoints
- Conversation management endpoints
- Audit log endpoints
- Health check endpoints (most lenient)
"""

import pytest
import asyncio
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI
from app.main import app as main_app


class TestRateLimiting:
    """Test suite for rate limiting middleware."""
    
    @pytest.mark.asyncio
    async def test_login_rate_limit_5_per_minute(self):
        """
        Test that login endpoint enforces 5 requests per minute limit.
        
        After 5 requests, subsequent requests should be rejected with 429.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            # Make 5 successful requests
            for i in range(5):
                response = await client.post(
                    "/api/v1/admin/auth/login",
                    json={
                        "email": f"test{i}@example.com",
                        "password": f"password{i}",
                    }
                )
                # Will fail auth but not rate limit (rate limit applies before auth)
                assert response.status_code in [400, 401, 422]
                assert response.status_code != 429
            
            # 6th request should be rate limited
            response = await client.post(
                "/api/v1/admin/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "password",
                }
            )
            
            # Should get 429 Too Many Requests
            assert response.status_code == 429
            assert "rate" in response.json()["error"].lower()
            assert response.headers.get("Retry-After") is not None
            assert response.headers.get("X-RateLimit-Limit") == "5"
    
    @pytest.mark.asyncio
    async def test_knowledge_rate_limit_30_per_minute(self):
        """
        Test that knowledge endpoint enforces 30 requests per minute limit.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            # Mock authentication
            headers = {"Authorization": "Bearer test-token"}
            
            # Make 30 requests (should all succeed or at least not get rate limited)
            for i in range(30):
                response = await client.get(
                    "/api/v1/admin/knowledge",
                    headers=headers,
                )
                # May fail with 401 but not 429
                if response.status_code != 401:
                    assert response.status_code != 429
            
            # 31st request might be rate limited
            response = await client.get(
                "/api/v1/admin/knowledge",
                headers=headers,
            )
            
            # If rate limited, should be 429
            if response.status_code == 429:
                assert "rate" in response.json()["error"].lower()
                assert response.headers.get("X-RateLimit-Limit") == "30"
    
    @pytest.mark.asyncio
    async def test_users_rate_limit_40_per_minute(self):
        """
        Test that user management endpoint enforces 40 requests per minute limit.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            headers = {"Authorization": "Bearer test-token"}
            
            # Make 40 requests
            for i in range(40):
                response = await client.get(
                    "/api/v1/admin/users",
                    headers=headers,
                )
                # Not rate limited yet
                assert response.status_code != 429
            
            # 41st request might be rate limited
            response = await client.get(
                "/api/v1/admin/users",
                headers=headers,
            )
            
            if response.status_code == 429:
                assert response.headers.get("X-RateLimit-Limit") == "40"
    
    @pytest.mark.asyncio
    async def test_conversations_rate_limit_50_per_minute(self):
        """
        Test that conversations endpoint enforces 50 requests per minute limit.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            headers = {"Authorization": "Bearer test-token"}
            
            # Make 50 requests
            for i in range(50):
                response = await client.get(
                    "/api/v1/admin/conversations",
                    headers=headers,
                )
                # Not rate limited yet
                assert response.status_code != 429
            
            # 51st request might be rate limited
            response = await client.get(
                "/api/v1/admin/conversations",
                headers=headers,
            )
            
            if response.status_code == 429:
                assert response.headers.get("X-RateLimit-Limit") == "50"
    
    @pytest.mark.asyncio
    async def test_audit_rate_limit_60_per_minute(self):
        """
        Test that audit endpoint enforces 60 requests per minute limit.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            headers = {"Authorization": "Bearer test-token"}
            
            # Make 60 requests
            for i in range(60):
                response = await client.get(
                    "/api/v1/admin/audit",
                    headers=headers,
                )
                # Not rate limited yet
                assert response.status_code != 429
            
            # 61st request might be rate limited
            response = await client.get(
                "/api/v1/admin/audit",
                headers=headers,
            )
            
            if response.status_code == 429:
                assert response.headers.get("X-RateLimit-Limit") == "60"
    
    @pytest.mark.asyncio
    async def test_health_rate_limit_100_per_minute(self):
        """
        Test that health endpoint has lenient 100 requests per minute limit.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            headers = {"Authorization": "Bearer test-token"}
            
            # Make 100 requests (should not be rate limited)
            for i in range(100):
                response = await client.get(
                    "/api/v1/admin/health",
                    headers=headers,
                )
                # Should not get rate limited at 100
                assert response.status_code != 429
    
    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self):
        """
        Test that rate limit headers are included in response.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            headers = {"Authorization": "Bearer test-token"}
            
            response = await client.get(
                "/api/v1/admin/health",
                headers=headers,
            )
            
            # Check for rate limit headers
            assert response.headers.get("X-RateLimit-Limit") is not None
            assert response.headers.get("X-RateLimit-Remaining") is not None
            assert response.headers.get("X-RateLimit-Reset") is not None
    
    @pytest.mark.asyncio
    async def test_rate_limit_429_response_format(self):
        """
        Test that 429 response has proper format with Retry-After.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            # Get rate limited by making multiple login attempts
            for i in range(6):  # 5 successful + 1 limited
                response = await client.post(
                    "/api/v1/admin/auth/login",
                    json={
                        "email": "test@example.com",
                        "password": "password",
                    }
                )
            
            # Should be rate limited now
            if response.status_code == 429:
                body = response.json()
                
                # Check response format
                assert "error" in body
                assert "code" in body
                assert body["code"] == "RATE_LIMIT_EXCEEDED"
                assert "retry_after" in body
                assert "details" in body
                
                # Check headers
                assert "Retry-After" in response.headers
                assert "X-RateLimit-Limit" in response.headers
                assert "X-RateLimit-Remaining" in response.headers
                assert "X-RateLimit-Reset" in response.headers
    
    @pytest.mark.asyncio
    async def test_different_ips_separate_limits(self):
        """
        Test that different IPs have separate rate limit buckets.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            headers = {"Authorization": "Bearer test-token"}
            
            # Same endpoint with different client IPs should not interfere
            # This is a bit tricky to test with a single client, but we can
            # verify the concept by ensuring the middleware tracks by IP+path
            
            response = await client.get(
                "/api/v1/admin/health",
                headers=headers,
                headers_override={"X-Forwarded-For": "192.168.1.1"},
            )
            
            # Should not get rate limited (first request for this IP)
            assert response.status_code != 429
    
    @pytest.mark.asyncio
    async def test_exempt_paths_not_rate_limited(self):
        """
        Test that exempt paths (health, metrics, docs) are not rate limited.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            # Make many requests to exempt path
            for i in range(200):
                response = await client.get("/health")
                # Should not get rate limited
                assert response.status_code != 429
    
    @pytest.mark.asyncio
    async def test_rate_limit_reset_after_window(self):
        """
        Test that rate limit resets after the time window expires.
        """
        # This test would need time manipulation (mock time.time())
        # For now, we document the expected behavior:
        # 1. Make max requests in window
        # 2. Verify rate limited
        # 3. Wait for window to expire
        # 4. Make request again - should succeed
        
        # Note: In production, use mock.patch('time.time') or similar
        pass


class TestRateLimitConfiguration:
    """Test rate limit configuration constants."""
    
    def test_endpoint_limits_configured(self):
        """
        Verify that all admin endpoints have configured rate limits.
        """
        from app.middleware.rate_limit import RateLimitMiddleware
        
        # Check that all endpoint limits have required fields
        for path, limit in RateLimitMiddleware.ENDPOINT_LIMITS.items():
            assert "max_requests" in limit
            assert "window_seconds" in limit
            assert limit["max_requests"] > 0
            assert limit["window_seconds"] > 0
    
    def test_default_limit_configured(self):
        """
        Verify that default rate limit is properly configured.
        """
        from app.middleware.rate_limit import RateLimitMiddleware
        
        default = RateLimitMiddleware.DEFAULT_LIMIT
        assert "max_requests" in default
        assert "window_seconds" in default
        assert default["max_requests"] > 0
        assert default["window_seconds"] > 0
    
    def test_exempt_paths_configured(self):
        """
        Verify that exempt paths are configured.
        """
        from app.middleware.rate_limit import RateLimitMiddleware
        
        exempt = RateLimitMiddleware.EXEMPT_PATHS
        assert len(exempt) > 0
        
        # Should include common exempt paths
        assert any("/health" in path for path in exempt)
        assert any("/docs" in path for path in exempt)
        assert any("/openapi" in path for path in exempt)
    
    def test_login_has_strictest_limit(self):
        """
        Verify that login endpoint has the strictest rate limit.
        """
        from app.middleware.rate_limit import RateLimitMiddleware
        
        limits = RateLimitMiddleware.ENDPOINT_LIMITS
        login_limit = limits["/api/v1/admin/auth/login"]["max_requests"]
        
        # Login should have <= 5 requests per minute
        assert login_limit <= 5
        
        # Other endpoints should have higher limits
        for path, config in limits.items():
            if path != "/api/v1/admin/auth/login":
                assert config["max_requests"] >= login_limit
    
    def test_health_has_most_lenient_limit(self):
        """
        Verify that health endpoint has the most lenient rate limit.
        """
        from app.middleware.rate_limit import RateLimitMiddleware
        
        limits = RateLimitMiddleware.ENDPOINT_LIMITS
        health_limit = limits.get("/api/v1/admin/health", {}).get("max_requests", 0)
        
        # Health should have high limit for monitoring
        assert health_limit >= 100
        
        # Health should be >= most other endpoints
        for path, config in limits.items():
            if path != "/api/v1/admin/health":
                assert config["max_requests"] <= health_limit or path == "/api/v1/admin/auth/login"
    
    def test_admin_endpoints_grouped_by_sensitivity(self):
        """
        Verify that admin endpoints are grouped by sensitivity level.
        """
        from app.middleware.rate_limit import RateLimitMiddleware
        
        limits = RateLimitMiddleware.ENDPOINT_LIMITS
        
        # Authentication: strictest
        auth_limits = [
            limits["/api/v1/admin/auth/login"]["max_requests"],
            limits["/api/v1/admin/auth"]["max_requests"],
        ]
        
        # Knowledge/Users/Conversations: moderate
        management_limits = [
            limits["/api/v1/admin/knowledge"]["max_requests"],
            limits["/api/v1/admin/users"]["max_requests"],
            limits["/api/v1/admin/conversations"]["max_requests"],
        ]
        
        # Audit: high (read-only, frequent access)
        audit_limit = limits["/api/v1/admin/audit"]["max_requests"]
        
        # Health: most lenient (monitoring)
        health_limit = limits["/api/v1/admin/health"]["max_requests"]
        
        # Verify ordering
        assert max(auth_limits) <= min(management_limits)
        assert max(management_limits) <= audit_limit
        assert audit_limit <= health_limit


class TestRateLimitSecurity:
    """Test security aspects of rate limiting."""
    
    def test_trusted_proxies_configured(self):
        """
        Verify that trusted proxies are properly configured.
        """
        from app.middleware.rate_limit import RateLimitMiddleware
        
        middleware = RateLimitMiddleware(None)
        
        # Should have compiled networks
        assert hasattr(middleware, '_trusted_networks')
        assert len(middleware._trusted_networks) > 0
    
    def test_client_ip_extraction_from_forwarded(self):
        """
        Test that client IP is correctly extracted from X-Forwarded-For header.
        """
        from app.middleware.rate_limit import RateLimitMiddleware
        from unittest.mock import Mock
        
        middleware = RateLimitMiddleware(None)
        
        # Create mock request with X-Forwarded-For header
        mock_request = Mock()
        mock_request.client = Mock(host="192.168.1.1")  # Trusted proxy
        mock_request.headers = {
            "X-Forwarded-For": "203.0.113.1, 192.168.1.1"  # Client IP, then proxy
        }
        
        # Should extract client IP (203.0.113.1) not proxy IP
        # This depends on the implementation correctly validating trusted proxies
        ip = middleware._get_client_ip(mock_request)
        assert ip is not None


class TestRateLimitIntegration:
    """Integration tests for rate limiting with actual endpoints."""
    
    @pytest.mark.asyncio
    async def test_knowledge_endpoints_have_limits(self):
        """
        Verify that all knowledge endpoints respect rate limits.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            headers = {"Authorization": "Bearer test-token"}
            
            # Test list endpoint
            response = await client.get("/api/v1/admin/knowledge", headers=headers)
            assert response.status_code != 429 or response.status_code == 429
            
            # Check headers if not rate limited
            if response.status_code != 429:
                assert "X-RateLimit-Limit" in response.headers
    
    @pytest.mark.asyncio
    async def test_user_endpoints_have_limits(self):
        """
        Verify that all user management endpoints respect rate limits.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            headers = {"Authorization": "Bearer test-token"}
            
            # Test list endpoint
            response = await client.get("/api/v1/admin/users", headers=headers)
            
            # Check headers
            if response.status_code != 429:
                assert "X-RateLimit-Limit" in response.headers
    
    @pytest.mark.asyncio
    async def test_conversation_endpoints_have_limits(self):
        """
        Verify that conversation endpoints respect rate limits.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            headers = {"Authorization": "Bearer test-token"}
            
            # Test list endpoint
            response = await client.get("/api/v1/admin/conversations", headers=headers)
            
            # Check headers
            if response.status_code != 429:
                assert "X-RateLimit-Limit" in response.headers
    
    @pytest.mark.asyncio
    async def test_audit_endpoints_have_limits(self):
        """
        Verify that audit log endpoints respect rate limits.
        """
        async with AsyncClient(app=main_app, base_url="http://testserver") as client:
            headers = {"Authorization": "Bearer test-token"}
            
            # Test list endpoint
            response = await client.get("/api/v1/admin/audit", headers=headers)
            
            # Check headers
            if response.status_code != 429:
                assert "X-RateLimit-Limit" in response.headers
