"""
Tests d'authentification et 2FA — BARROW.AI.

Scope limité : uniquement les tests qui ne nécessitent pas
de connexion DB ou Redis active.

Ce qui fonctionne sans infrastructure :
1. CSRF middleware (403) — s'exécute avant résolution des dépendances FastAPI
2. CSRF exempt checks — auth endpoints exempts de CSRF
3. Endpoint CSRF token (GET, aucune dépendance)

Note: Les tests Pydantic (422), JWT (401) et les flux login complets
nécessitent la DB et Redis. Ils sont dans test_admin_api.py avec
les fixtures appropriées.
"""

import pytest
from uuid import uuid4


# ─── 1. CSRF middleware — avant résolution des dépendances ────────

class TestCsrfMiddlewareOnProtectedEndpoints:
    """Le middleware CSRF retourne 403 avant toute connexion DB.
    Ces tests fonctionnent sans PostgreSQL ni Redis."""

    def test_post_users_without_csrf_returns_403(self, sync_client):
        """POST /users sans cookie CSRF → 403."""
        res = sync_client.post(
            "/api/v1/admin/users",
            json={"email": "x@x.com", "password": "X123!", "role": "VIEWER"},
            cookies={},
        )
        assert res.status_code == 403

    def test_delete_user_without_csrf_returns_403(self, sync_client):
        """DELETE /users/{id} sans cookie CSRF → 403."""
        res = sync_client.delete(
            f"/api/v1/admin/users/{uuid4()}",
            cookies={},
        )
        assert res.status_code == 403

    def test_put_user_without_csrf_returns_403(self, sync_client):
        """PUT /users/{id} sans cookie CSRF → 403."""
        res = sync_client.put(
            f"/api/v1/admin/users/{uuid4()}",
            json={"full_name": "x"},
            cookies={},
        )
        assert res.status_code == 403

    def test_post_knowledge_without_csrf_returns_403(self, sync_client):
        """POST /knowledge sans cookie CSRF → 403."""
        res = sync_client.post("/api/v1/admin/knowledge", cookies={})
        assert res.status_code == 403

    def test_delete_knowledge_without_csrf_returns_403(self, sync_client):
        """DELETE /knowledge/{id} sans cookie CSRF → 403."""
        res = sync_client.delete(
            f"/api/v1/admin/knowledge/{uuid4()}",
            cookies={},
        )
        assert res.status_code == 403

    def test_post_with_wrong_csrf_header_returns_403(self, sync_client):
        """Header CSRF ne correspondant pas au cookie → 403."""
        # Poser un cookie légitime
        sync_client.get("/api/v1/admin/auth/csrf-token")
        res = sync_client.post(
            "/api/v1/admin/users",
            headers={"X-CSRF-Token": "wrong-token"},
            json={"email": "x@x.com", "password": "X", "role": "VIEWER"},
        )
        assert res.status_code == 403

    def test_post_with_empty_csrf_header_returns_403(self, sync_client):
        """Header X-CSRF-Token vide (avec cookie présent) → 403."""
        sync_client.get("/api/v1/admin/auth/csrf-token")
        res = sync_client.post(
            "/api/v1/admin/users",
            headers={"X-CSRF-Token": ""},
            json={"email": "x@x.com", "password": "X", "role": "VIEWER"},
        )
        assert res.status_code == 403

    def test_post_with_valid_csrf_passes_middleware(self, sync_client):
        """POST avec CSRF token valide → pas de 403 (peut être 401/422/500)."""
        csrf_res = sync_client.get("/api/v1/admin/auth/csrf-token")
        csrf_token = csrf_res.json()["csrf_token"]
        res = sync_client.post(
            "/api/v1/admin/users",
            headers={"X-CSRF-Token": csrf_token},
            json={"email": "x@test.com", "password": "X123!", "role": "VIEWER"},
        )
        # Le CSRF passe — peut être 401, 422, ou 500 (DB), mais PAS 403
        assert res.status_code != 403


# ─── 2. Endpoints auth exempts de CSRF ───────────────────────────

class TestAuthEndpointsExemptFromCsrf:
    """POST sur les endpoints auth ne doivent pas retourner 403 CSRF.
    Ils peuvent retourner 422 (validation) ou autre, mais pas 403 (CSRF)."""

    def test_login_endpoint_is_csrf_exempt(self, sync_client):
        """POST /auth/login — exempt de CSRF (pas encore de session)."""
        res = sync_client.post(
            "/api/v1/admin/auth/login",
            json={"email": "x@x.com", "password": "wrong"},
            cookies={},
        )
        assert res.status_code != 403

    def test_verify_2fa_endpoint_is_csrf_exempt(self, sync_client):
        """POST /auth/verify-2fa — exempt de CSRF."""
        res = sync_client.post(
            "/api/v1/admin/auth/verify-2fa",
            json={"session_token": "x", "two_factor_code": "123456"},
            cookies={},
        )
        assert res.status_code != 403

    def test_refresh_endpoint_is_csrf_exempt(self, sync_client):
        """POST /auth/refresh — exempt de CSRF."""
        res = sync_client.post(
            "/api/v1/admin/auth/refresh",
            json={"refresh_token": "invalid"},
            cookies={},
        )
        assert res.status_code != 403


# ─── 3. Endpoint CSRF token ───────────────────────────────────────

class TestCsrfTokenEndpointViaTwoFactor:
    """Tests redondants du endpoint CSRF pour la couverture du module auth."""

    def test_csrf_token_accessible(self, sync_client):
        """GET /auth/csrf-token → 200."""
        res = sync_client.get("/api/v1/admin/auth/csrf-token")
        assert res.status_code == 200

    def test_csrf_token_in_json(self, sync_client):
        """Le token est dans la réponse JSON."""
        data = sync_client.get("/api/v1/admin/auth/csrf-token").json()
        assert "csrf_token" in data
        assert len(data["csrf_token"]) >= 20

    def test_csrf_cookie_set_by_endpoint(self, sync_client):
        """Le cookie csrf_token est posé."""
        sync_client.get("/api/v1/admin/auth/csrf-token")
        assert "csrf_token" in sync_client.cookies

    def test_consecutive_tokens_differ(self, sync_client):
        """Deux tokens successifs sont différents (entropie)."""
        t1 = sync_client.get("/api/v1/admin/auth/csrf-token").json()["csrf_token"]
        t2 = sync_client.get("/api/v1/admin/auth/csrf-token").json()["csrf_token"]
        assert t1 != t2
