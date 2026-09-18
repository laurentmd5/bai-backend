"""
Tests d'intégration pour la protection CSRF — BARROW.AI.

Scope : uniquement les tests qui ne nécessitent pas de DB ni Redis.
Le middleware CSRF opère au niveau Starlette, avant la résolution
des dépendances FastAPI (avant toute connexion DB).

Pattern validé :
- GET csrf-token → token + cookie (pas de DB)
- POST/DELETE/PUT sans cookie CSRF → 403 (middleware avant DB)
- POST/DELETE/PUT avec cookie mais header invalide → 403
- Auth endpoints exempts de CSRF (login, verify-2fa, refresh)
"""

import pytest
from uuid import uuid4


# ─── 1. Token endpoint ────────────────────────────────────────────

class TestCsrfTokenEndpoint:
    """Tests du endpoint GET /auth/csrf-token."""

    def test_csrf_endpoint_returns_200(self, sync_client):
        res = sync_client.get("/api/v1/admin/auth/csrf-token")
        assert res.status_code == 200

    def test_csrf_endpoint_returns_token(self, sync_client):
        data = sync_client.get("/api/v1/admin/auth/csrf-token").json()
        assert "csrf_token" in data
        token = data["csrf_token"]
        assert isinstance(token, str) and len(token) >= 20

    def test_csrf_endpoint_sets_cookie(self, sync_client):
        sync_client.get("/api/v1/admin/auth/csrf-token")
        assert "csrf_token" in sync_client.cookies

    def test_csrf_tokens_are_unique(self, sync_client):
        t1 = sync_client.get("/api/v1/admin/auth/csrf-token").json()["csrf_token"]
        t2 = sync_client.get("/api/v1/admin/auth/csrf-token").json()["csrf_token"]
        assert t1 != t2

    def test_csrf_token_not_empty(self, sync_client):
        token = sync_client.get("/api/v1/admin/auth/csrf-token").json()["csrf_token"]
        assert token.strip() != ""


# ─── 2. Validation CSRF — middleware avant DB ─────────────────────

class TestCsrfValidationOnWriteMethods:
    """Le middleware CSRF s'exécute avant toute résolution de dépendance DB."""

    def test_post_without_csrf_cookie_returns_403(self, sync_client):
        """POST sans cookie csrf_token → 403 CSRF."""
        res = sync_client.post(
            "/api/v1/admin/users",
            json={"email": "x@x.com", "password": "X", "role": "VIEWER"},
            cookies={},
        )
        assert res.status_code == 403

    def test_post_with_mismatched_csrf_returns_403(self, sync_client):
        """POST avec cookie CSRF mais header ne correspondant pas → 403."""
        # Obtenir et poser le cookie
        sync_client.get("/api/v1/admin/auth/csrf-token")
        # Envoyer un header différent du cookie
        res = sync_client.post(
            "/api/v1/admin/users",
            headers={"X-CSRF-Token": "wrong-token-does-not-match"},
            json={"email": "x@x.com", "password": "X", "role": "VIEWER"},
        )
        assert res.status_code == 403

    def test_post_with_empty_csrf_header_returns_403(self, sync_client):
        """POST avec header X-CSRF-Token vide → 403."""
        sync_client.get("/api/v1/admin/auth/csrf-token")
        res = sync_client.post(
            "/api/v1/admin/users",
            headers={"X-CSRF-Token": ""},
            json={"email": "x@x.com", "password": "X", "role": "VIEWER"},
        )
        assert res.status_code == 403

    def test_delete_without_csrf_returns_403(self, sync_client):
        """DELETE sans cookie CSRF → 403."""
        res = sync_client.delete(
            f"/api/v1/admin/users/{uuid4()}",
            cookies={},
        )
        assert res.status_code == 403

    def test_put_without_csrf_returns_403(self, sync_client):
        """PUT sans cookie CSRF → 403."""
        res = sync_client.put(
            f"/api/v1/admin/users/{uuid4()}",
            json={"full_name": "x"},
            cookies={},
        )
        assert res.status_code == 403

    def test_patch_without_csrf_returns_403(self, sync_client):
        """PATCH sans cookie CSRF → 403."""
        res = sync_client.patch(
            f"/api/v1/admin/users/{uuid4()}",
            json={"is_active": False},
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


# ─── 3. CSRF valide → pas de 403 (peut retourner 401 auth etc.) ──

class TestCsrfValidTokenPassesValidation:
    """Avec un token CSRF valide, le middleware laisse passer (pas de 403)."""

    def test_post_with_matching_csrf_not_403(self, sync_client):
        """POST avec header = cookie CSRF → pas de 403 (peut être 401 auth)."""
        csrf_res = sync_client.get("/api/v1/admin/auth/csrf-token")
        csrf_token = csrf_res.json()["csrf_token"]
        res = sync_client.post(
            "/api/v1/admin/users",
            headers={"X-CSRF-Token": csrf_token},
            json={"email": "x@test.com", "password": "X123!", "role": "VIEWER"},
        )
        # Le CSRF passe — peut retourner 401 (auth), 422 (validation), mais pas 403 (CSRF)
        assert res.status_code != 403

    def test_delete_with_valid_csrf_not_403(self, sync_client):
        """DELETE avec CSRF valide → pas de 403."""
        csrf_res = sync_client.get("/api/v1/admin/auth/csrf-token")
        csrf_token = csrf_res.json()["csrf_token"]
        res = sync_client.delete(
            f"/api/v1/admin/users/{uuid4()}",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert res.status_code != 403


# ─── 4. Endpoints exempts de CSRF ─────────────────────────────────

class TestCsrfExemptEndpoints:
    """Certains endpoints sont explicitement exemptés du CSRF (auth flow)."""

    def test_login_exempt_no_cookie_needed(self, sync_client):
        """POST /auth/login est exempt de CSRF → ne retourne pas 403."""
        res = sync_client.post(
            "/api/v1/admin/auth/login",
            json={"email": "x@x.com", "password": "wrong"},
            cookies={},
        )
        assert res.status_code != 403

    def test_verify_2fa_exempt(self, sync_client):
        """POST /auth/verify-2fa est exempt de CSRF."""
        res = sync_client.post(
            "/api/v1/admin/auth/verify-2fa",
            json={"session_token": "x", "two_factor_code": "123456"},
            cookies={},
        )
        assert res.status_code != 403

    def test_refresh_exempt(self, sync_client):
        """POST /auth/refresh est exempt de CSRF."""
        res = sync_client.post(
            "/api/v1/admin/auth/refresh",
            json={"refresh_token": "invalid"},
            cookies={},
        )
        assert res.status_code != 403
