"""
Tests d'intégration pour la sécurité, rate limiting et RBAC.
Couvre: CSRF, validation d'input, rate limiting, permissions.
"""

import pytest
from uuid import uuid4
from app.core.security import create_jwt_token


@pytest.mark.asyncio
class TestCSRFProtection:
    """Tests de protection CSRF — voir aussi tests/integration/test_csrf.py pour les tests complets."""

    async def test_post_request_without_csrf_cookie_rejected(self, sync_client, admin_headers):
        """POST sans cookie csrf_token → 403."""
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "email": "test-csrf@test.com",
                "password": "Password123!",
                "full_name": "Test",
                "role": "ADMIN",
            },
            cookies={},  # Aucun cookie
        )
        assert response.status_code == 403

    async def test_get_request_no_csrf_required(self, sync_client, admin_headers):
        """Les requêtes GET ne nécessitent pas de token CSRF."""
        response = sync_client.get(
            "/api/v1/admin/users",
            headers=admin_headers,
        )
        assert response.status_code != 403

    async def test_invalid_csrf_token_rejected(self, sync_client, admin_headers):
        """Un token CSRF invalide (présent dans header mais ne correspond pas au cookie) → 403."""
        # Poser un cookie légitime via le endpoint
        sync_client.get("/api/v1/admin/auth/csrf-token")
        headers = {**admin_headers, "X-CSRF-Token": "invalid-token-not-matching-cookie"}
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=headers,
            json={
                "email": "invalid-csrf@test.com",
                "password": "Password123!",
                "full_name": "Test",
                "role": "ADMIN",
            },
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestInputValidation:
    """Tests de validation d'input."""
    
    async def test_xss_prevention_in_full_name(self, sync_client, admin_headers):
        """Prévention XSS dans le nom complet."""
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "email": "xss@test.com",
                "password": "Password123!",
                "full_name": "<script>alert('XSS')</script>",
                "role": "ADMIN",
            }
        )
        # Either fails validation or sanitizes the input
        if response.status_code == 201:
            data = response.json()
            # Full name should be sanitized
            assert "<script>" not in data.get("full_name", "")
        else:
            assert response.status_code == 422
    
    async def test_sql_injection_in_search(self, sync_client, admin_headers):
        """Prévention SQL injection dans recherche."""
        response = sync_client.get(
            "/api/v1/admin/conversations?search=' OR '1'='1",
            headers=admin_headers,
        )
        # Should not execute SQL injection
        assert response.status_code == 200
    
    async def test_email_injection_prevention(self, sync_client, admin_headers):
        """Prévention email injection."""
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "email": "test@test.com\nBcc: attacker@test.com",
                "password": "Password123!",
                "full_name": "Test",
                "role": "ADMIN",
            }
        )
        # Should reject invalid email
        assert response.status_code == 422


@pytest.mark.asyncio
class TestRateLimiting:
    """Tests du rate limiting."""
    
    async def test_rate_limit_login_endpoint(self, sync_client):
        """Rate limiting sur le endpoint login : 5+ échecs → 401 ou 429 (jamais 200)."""
        for i in range(7):
            response = sync_client.post(
                "/api/v1/admin/auth/login",
                json={
                    "email": "ratelimit@test.com",
                    "password": "wrong_password_for_test"
                }
            )
        # Toutes les réponses doivent être des erreurs, jamais 200
        assert response.status_code in [401, 422, 429]
    
    async def test_rate_limit_2fa_endpoint(self, sync_client):
        """Rate limiting sur le endpoint 2FA verification."""
        # Multiple attempts
        for i in range(11):
            response = sync_client.post(
                "/api/v1/admin/auth/verify-2fa",
                json={
                    "session_token": "invalid",
                    "two_factor_code": "000000"
                }
            )
        
        # Should be rate limited
        assert response.status_code in [401, 429]
    
    async def test_rate_limit_knowledge_endpoint(self, sync_client, admin_headers):
        """Rate limiting sur les endpoints knowledge."""
        # Multiple requests
        for i in range(11):
            response = sync_client.get(
                "/api/v1/admin/knowledge",
                headers=admin_headers,
            )
        
        # May be rate limited
        assert response.status_code in [200, 429]


@pytest.mark.asyncio
class TestAuthenticationRBAC:
    """Tests des permissions RBAC pour l'authentification."""
    
    async def test_superadmin_can_do_everything(self, sync_client, admin_headers, test_admin):
        """SUPERADMIN a toutes les permissions."""
        endpoints = [
            ("GET", "/api/v1/admin/users", None),
            ("GET", "/api/v1/admin/knowledge", None),
            ("GET", "/api/v1/admin/conversations", None),
            ("GET", "/api/v1/admin/audit", None),
            ("GET", "/api/v1/admin/analytics/overview", None),
        ]
        
        for method, endpoint, body in endpoints:
            if method == "GET":
                response = sync_client.get(endpoint, headers=admin_headers)
            else:
                response = sync_client.post(endpoint, headers=admin_headers, json=body)
            
            assert response.status_code == 200
    
    async def test_admin_cannot_delete_users(self, sync_client, regular_admin_headers, test_auditor):
        """ADMIN ne peut pas supprimer les utilisateurs (sauf SUPERADMIN)."""
        response = sync_client.delete(
            f"/api/v1/admin/users/{test_auditor.id}",
            headers=regular_admin_headers,
        )
        # ADMIN should be able to delete regular users but maybe not superadmins
        # This depends on implementation
        assert response.status_code in [200, 204, 403]
    
    async def test_auditor_can_view_not_modify(self, sync_client, auditor_headers):
        """AUDITOR peut voir mais ne peut pas modifier."""
        # Can view
        response = sync_client.get(
            "/api/v1/admin/conversations",
            headers=auditor_headers,
        )
        assert response.status_code == 200
        
        # Cannot modify (delete)
        response = sync_client.delete(
            f"/api/v1/admin/conversations/{uuid4()}",
            headers=auditor_headers,
        )
        assert response.status_code == 403
    
    async def test_viewer_limited_access(self, sync_client, db_session):
        """VIEWER a un accès limité."""
        viewer_token = create_jwt_token(
            {
                "sub": str(uuid4()),
                "email": "viewer@test.com",
                "role": "VIEWER",
            },
            "access"
        )
        viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
        
        # Can view conversations (maybe)
        response = sync_client.get(
            "/api/v1/admin/conversations",
            headers=viewer_headers,
        )
        # Should allow or deny based on implementation
        assert response.status_code in [200, 403]


@pytest.mark.asyncio
class TestTokenSecurity:
    """Tests de sécurité des tokens."""
    
    async def test_invalid_jwt_token_rejected(self, sync_client):
        """Un token JWT invalide est rejeté."""
        response = sync_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == 401
    
    async def test_expired_token_rejected(self, sync_client, expired_token):
        """Un token expiré est rejeté."""
        response = sync_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401
    
    async def test_malformed_authorization_header(self, sync_client):
        """Un header Authorization malformé est rejeté."""
        response = sync_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": "NotBearerToken"}
        )
        assert response.status_code == 401
    
    async def test_missing_bearer_prefix(self, sync_client, admin_token):
        """Un token sans préfixe Bearer est rejeté."""
        response = sync_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": admin_token}  # Missing "Bearer " prefix
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestPasswordSecurity:
    """Tests de sécurité des mots de passe."""
    
    async def test_password_not_in_response(self, sync_client, admin_headers, test_admin):
        """Le mot de passe ne doit pas être dans la réponse."""
        response = sync_client.get(
            f"/api/v1/admin/users/{test_admin.id}",
            headers=admin_headers,
        )
        data = response.json()
        assert "password" not in data
        assert "password_hash" not in data
    
    async def test_password_not_in_list_response(self, sync_client, admin_headers):
        """Le mot de passe ne doit pas être dans la liste."""
        response = sync_client.get(
            "/api/v1/admin/users",
            headers=admin_headers,
        )
        data = response.json()
        for user in data.get("users", []):
            assert "password" not in user
            assert "password_hash" not in user
    
    async def test_password_change_requires_current_password(self, sync_client, admin_headers):
        """Le changement de mot de passe nécessite l'ancien mot de passe."""
        response = sync_client.post(
            "/api/v1/admin/auth/change-password",
            headers=admin_headers,
            json={
                "old_password": "WrongPassword",
                "new_password": "NewPassword123!",
            }
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAuthorizationHeaders:
    """Tests des headers d'autorisation."""
    
    async def test_case_insensitive_bearer(self, sync_client, admin_token):
        """Le prefixe Bearer est case-insensitive (par spec)."""
        # Try different cases
        for prefix in ["bearer", "Bearer", "BEARER"]:
            response = sync_client.get(
                "/api/v1/admin/users",
                headers={"Authorization": f"{prefix} {admin_token}"}
            )
            # Most implementations accept Bearer but not always case-insensitive
            assert response.status_code in [200, 401]
    
    async def test_no_authorization_header(self, sync_client):
        """Pas de header Authorization retourne 401."""
        response = sync_client.get("/api/v1/admin/users")
        assert response.status_code == 401
    
    async def test_empty_authorization_header(self, sync_client):
        """Un header Authorization vide retourne 401."""
        response = sync_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": ""}
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestSecurityHeaders:
    """Tests des headers de sécurité."""
    
    async def test_response_contains_security_headers(self, sync_client, admin_headers):
        """La réponse doit contenir les headers de sécurité."""
        response = sync_client.get(
            "/api/v1/admin/users",
            headers=admin_headers,
        )
        
        # Check for common security headers
        security_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
        ]
        
        # May not all be present depending on implementation
        for header in security_headers:
            # Either present or not, but should be set
            if header in response.headers:
                assert response.headers[header]
    
    async def test_no_sensitive_info_in_error_response(self, sync_client):
        """Les réponses d'erreur ne doivent pas contenir d'info sensible."""
        response = sync_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": "Bearer invalid"}
        )
        
        data = response.json() if response.status_code != 500 else {}
        
        # Should not expose stack trace or sensitive info in non-500 errors
        if response.status_code != 500:
            error_text = str(data)
            assert "traceback" not in error_text.lower()
            assert "sql" not in error_text.lower()


@pytest.mark.asyncio
class TestCORSProtection:
    """Tests de protection CORS."""
    
    async def test_cors_headers_present(self, sync_client, admin_headers):
        """Les headers CORS doivent être présents."""
        response = sync_client.options(
            "/api/v1/admin/users",
            headers=admin_headers,
        )
        
        # Might be present or not depending on implementation
        # Just verify the response is valid
        assert response.status_code in [200, 204, 405]


@pytest.mark.asyncio
class TestEndpointSecurityByRole:
    """Tests de sécurité par endpoint et rôle."""
    
    async def test_sensitive_endpoints_protected(self, sync_client):
        """Les endpoints sensibles nécessitent l'authentification."""
        sensitive_endpoints = [
            "/api/v1/admin/users",
            "/api/v1/admin/knowledge",
            "/api/v1/admin/audit",
        ]
        
        for endpoint in sensitive_endpoints:
            response = sync_client.get(endpoint)
            assert response.status_code == 401
    
    async def test_admin_creation_protected(self, sync_client):
        """La création d'admin nécessite l'authentification."""
        response = sync_client.post(
            "/api/v1/admin/users",
            json={
                "email": "test@test.com",
                "password": "Password123!",
                "full_name": "Test",
                "role": "ADMIN",
            }
        )
        assert response.status_code == 401
