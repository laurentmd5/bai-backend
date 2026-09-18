"""
Tests d'intégration pour les endpoints d'authentification.
Couvre: login, 2FA, refresh, logout, change password.
"""

import json
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
import pyotp

from app.models.domain.admin import AdminUser
from app.core.security import (
    hash_password,
    create_jwt_token,
    generate_totp_secret,
    verify_totp,
)


@pytest.mark.asyncio
class TestAuthLogin:
    """Tests du login (endpoint POST /api/v1/admin/auth/login)."""
    
    async def test_login_success_without_2fa(self, sync_client, test_admin):
        """Login réussi sans 2FA."""
        response = sync_client.post(
            "/api/v1/admin/auth/login",
            json={
                "email": test_admin.email,
                "password": "AdminTest123!",
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["access_token_expires_in"] == 3600
        assert data["requires_2fa"] is False
    
    async def test_login_with_2fa_enabled(self, sync_client, db_session):
        """Login avec 2FA activée retourne session_token."""
        # Create admin with 2FA
        admin_with_2fa = AdminUser(
            id=uuid4(),
            email="2fa@test.com",
            full_name="2FA Admin",
            password_hash=hash_password("Password123!"),
            role="SUPERADMIN",
            is_active=True,
            two_factor_enabled=True,
            two_factor_secret=generate_totp_secret(),
        )
        db_session.add(admin_with_2fa)
        await db_session.commit()
        
        response = sync_client.post(
            "/api/v1/admin/auth/login",
            json={
                "email": "2fa@test.com",
                "password": "Password123!",
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["requires_2fa"] is True
        assert "session_token" in data
    
    async def test_login_invalid_email(self, sync_client):
        """Login avec email invalide retourne 401."""
        response = sync_client.post(
            "/api/v1/admin/auth/login",
            json={
                "email": "nonexistent@test.com",
                "password": "Password123!",
            }
        )
        assert response.status_code == 401
        assert "invalid credentials" in response.json()["detail"].lower()
    
    async def test_login_invalid_password(self, sync_client, test_admin):
        """Login avec mauvais mot de passe retourne 401."""
        response = sync_client.post(
            "/api/v1/admin/auth/login",
            json={
                "email": test_admin.email,
                "password": "WrongPassword123!",
            }
        )
        assert response.status_code == 401
        assert "invalid credentials" in response.json()["detail"].lower()
    
    async def test_login_inactive_user(self, sync_client, db_session):
        """Login d'un utilisateur inactif retourne 403."""
        # Create inactive admin
        inactive_admin = AdminUser(
            id=uuid4(),
            email="inactive@test.com",
            full_name="Inactive Admin",
            password_hash=hash_password("Password123!"),
            role="ADMIN",
            is_active=False,
        )
        db_session.add(inactive_admin)
        await db_session.commit()
        
        response = sync_client.post(
            "/api/v1/admin/auth/login",
            json={
                "email": "inactive@test.com",
                "password": "Password123!",
            }
        )
        assert response.status_code == 403
        assert "inactive" in response.json()["detail"].lower()
    
    async def test_login_missing_email(self, sync_client):
        """Login sans email retourne 422."""
        response = sync_client.post(
            "/api/v1/admin/auth/login",
            json={"password": "Password123!"}
        )
        assert response.status_code == 422
    
    async def test_login_missing_password(self, sync_client):
        """Login sans mot de passe retourne 422."""
        response = sync_client.post(
            "/api/v1/admin/auth/login",
            json={"email": "test@test.com"}
        )
        assert response.status_code == 422
    
    async def test_login_account_locked(self, sync_client, db_session):
        """Login avec compte verrouillé retourne 429."""
        # Create locked admin
        locked_admin = AdminUser(
            id=uuid4(),
            email="locked@test.com",
            full_name="Locked Admin",
            password_hash=hash_password("Password123!"),
            role="ADMIN",
            is_active=True,
            failed_login_attempts=5,
            account_locked_until=datetime.utcnow() + timedelta(hours=1),
        )
        db_session.add(locked_admin)
        await db_session.commit()
        
        response = sync_client.post(
            "/api/v1/admin/auth/login",
            json={
                "email": "locked@test.com",
                "password": "Password123!",
            }
        )
        assert response.status_code == 429


@pytest.mark.asyncio
class TestAuthVerify2FA:
    """Tests du vérification 2FA (endpoint POST /api/v1/admin/auth/verify-2fa)."""
    
    async def test_verify_2fa_success(self, sync_client, db_session):
        """Vérification 2FA réussie."""
        # Create admin with 2FA
        secret = generate_totp_secret()
        admin_with_2fa = AdminUser(
            id=uuid4(),
            email="2fa@test.com",
            full_name="2FA Admin",
            password_hash=hash_password("Password123!"),
            role="SUPERADMIN",
            is_active=True,
            two_factor_enabled=True,
            two_factor_secret=secret,
        )
        db_session.add(admin_with_2fa)
        await db_session.commit()
        
        # Login to get session_token
        login_resp = sync_client.post(
            "/api/v1/admin/auth/login",
            json={
                "email": "2fa@test.com",
                "password": "Password123!",
            }
        )
        session_token = login_resp.json()["session_token"]
        
        # Generate valid 2FA code
        totp = pyotp.TOTP(secret)
        code = totp.now()
        
        # Verify 2FA
        response = sync_client.post(
            "/api/v1/admin/auth/verify-2fa",
            json={
                "session_token": session_token,
                "two_factor_code": code,
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
    
    async def test_verify_2fa_invalid_code(self, sync_client, db_session):
        """Vérification 2FA avec code invalide."""
        secret = generate_totp_secret()
        admin_with_2fa = AdminUser(
            id=uuid4(),
            email="2fa@test.com",
            full_name="2FA Admin",
            password_hash=hash_password("Password123!"),
            role="SUPERADMIN",
            is_active=True,
            two_factor_enabled=True,
            two_factor_secret=secret,
        )
        db_session.add(admin_with_2fa)
        await db_session.commit()
        
        login_resp = sync_client.post(
            "/api/v1/admin/auth/login",
            json={
                "email": "2fa@test.com",
                "password": "Password123!",
            }
        )
        session_token = login_resp.json()["session_token"]
        
        response = sync_client.post(
            "/api/v1/admin/auth/verify-2fa",
            json={
                "session_token": session_token,
                "two_factor_code": "000000",  # Invalid code
            }
        )
        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()
    
    async def test_verify_2fa_expired_session(self, sync_client):
        """Vérification 2FA avec session expirée."""
        response = sync_client.post(
            "/api/v1/admin/auth/verify-2fa",
            json={
                "session_token": "invalid-token",
                "two_factor_code": "123456",
            }
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAuthRefresh:
    """Tests du refresh token (endpoint POST /api/v1/admin/auth/refresh)."""
    
    async def test_refresh_token_success(self, sync_client, test_admin):
        """Refresh token réussi."""
        # Get initial tokens
        login_resp = sync_client.post(
            "/api/v1/admin/auth/login",
            json={
                "email": test_admin.email,
                "password": "AdminTest123!",
            }
        )
        refresh_token = login_resp.json()["refresh_token"]
        
        # Refresh
        response = sync_client.post(
            "/api/v1/admin/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    async def test_refresh_invalid_token(self, sync_client):
        """Refresh avec token invalide."""
        response = sync_client.post(
            "/api/v1/admin/auth/refresh",
            json={"refresh_token": "invalid-token"}
        )
        assert response.status_code == 401
    
    async def test_refresh_expired_token(self, sync_client, expired_token):
        """Refresh avec token expiré."""
        response = sync_client.post(
            "/api/v1/admin/auth/refresh",
            json={"refresh_token": expired_token}
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAuthLogout:
    """Tests du logout (endpoint POST /api/v1/admin/auth/logout)."""
    
    async def test_logout_success(self, sync_client, admin_headers):
        """Logout réussi."""
        response = sync_client.post(
            "/api/v1/admin/auth/logout",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Logout successful"
    
    async def test_logout_without_auth(self, sync_client):
        """Logout sans authentification."""
        response = sync_client.post("/api/v1/admin/auth/logout")
        assert response.status_code == 401
    
    async def test_logout_blacklists_token(self, sync_client, admin_headers):
        """Logout blacklist le token."""
        # Logout
        sync_client.post(
            "/api/v1/admin/auth/logout",
            headers=admin_headers,
        )
        
        # Try to use token after logout - should fail
        response = sync_client.get(
            "/api/v1/admin/auth/me",
            headers=admin_headers,
        )
        # Token should be blacklisted
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAuthChangePassword:
    """Tests du changement de mot de passe (endpoint POST /api/v1/admin/auth/change-password)."""
    
    async def test_change_password_success(self, sync_client, test_admin, admin_headers):
        """Changement de mot de passe réussi."""
        response = sync_client.post(
            "/api/v1/admin/auth/change-password",
            headers=admin_headers,
            json={
                "old_password": "AdminTest123!",
                "new_password": "NewPassword123!",
            }
        )
        assert response.status_code == 200
    
    async def test_change_password_wrong_old_password(self, sync_client, admin_headers):
        """Changement de mot de passe avec ancien mot de passe incorrect."""
        response = sync_client.post(
            "/api/v1/admin/auth/change-password",
            headers=admin_headers,
            json={
                "old_password": "WrongPassword123!",
                "new_password": "NewPassword123!",
            }
        )
        assert response.status_code == 401
    
    async def test_change_password_weak_new_password(self, sync_client, admin_headers):
        """Changement de mot de passe avec nouveau mot de passe faible."""
        response = sync_client.post(
            "/api/v1/admin/auth/change-password",
            headers=admin_headers,
            json={
                "old_password": "AdminTest123!",
                "new_password": "123",  # Too weak
            }
        )
        assert response.status_code == 422
    
    async def test_change_password_without_auth(self, sync_client):
        """Changement de mot de passe sans authentification."""
        response = sync_client.post(
            "/api/v1/admin/auth/change-password",
            json={
                "old_password": "AdminTest123!",
                "new_password": "NewPassword123!",
            }
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAuthGetMe:
    """Tests de récupération des informations utilisateur actuels (endpoint GET /api/v1/admin/auth/me)."""
    
    async def test_get_me_success(self, sync_client, test_admin, admin_headers):
        """Récupération des infos utilisateur réussies."""
        response = sync_client.get(
            "/api/v1/admin/auth/me",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_admin.email
        assert data["role"] == "SUPERADMIN"
        assert data["full_name"] == test_admin.full_name
    
    async def test_get_me_without_auth(self, sync_client):
        """Récupération des infos sans authentification."""
        response = sync_client.get("/api/v1/admin/auth/me")
        assert response.status_code == 401
    
    async def test_get_me_with_invalid_token(self, sync_client):
        """Récupération des infos avec token invalide."""
        response = sync_client.get(
            "/api/v1/admin/auth/me",
            headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAuth2FASetup:
    """Tests de setup 2FA (endpoint POST /api/v1/admin/2fa/enable)."""
    
    async def test_setup_2fa_success(self, sync_client, test_admin, admin_headers):
        """Setup 2FA réussi."""
        response = sync_client.post(
            "/api/v1/admin/2fa/enable",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "secret" in data
        assert "qr_code_url" in data
    
    async def test_setup_2fa_verify_success(self, sync_client, admin_headers, db_session, test_admin):
        """Vérification 2FA après setup."""
        # Setup 2FA
        setup_resp = sync_client.post(
            "/api/v1/admin/2fa/enable",
            headers=admin_headers,
        )
        secret = setup_resp.json()["secret"]
        
        # Verify 2FA
        totp = pyotp.TOTP(secret)
        code = totp.now()
        
        response = sync_client.post(
            "/api/v1/admin/2fa/verify",
            headers=admin_headers,
            json={
                "two_factor_code": code,
            }
        )
        assert response.status_code == 200
        assert "backup_codes" in response.json()
    
    async def test_setup_2fa_without_auth(self, sync_client):
        """Setup 2FA sans authentification."""
        response = sync_client.post("/api/v1/admin/2fa/enable")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAuth2FADisable:
    """Tests de désactivation 2FA (endpoint POST /api/v1/admin/2fa/disable)."""
    
    async def test_disable_2fa_success(self, sync_client, db_session, admin_headers):
        """Désactivation 2FA réussie."""
        # First enable 2FA
        sync_client.post(
            "/api/v1/admin/2fa/enable",
            headers=admin_headers,
        )
        
        # Then disable it
        response = sync_client.post(
            "/api/v1/admin/2fa/disable",
            headers=admin_headers,
            json={"password": "AdminTest123!"}
        )
        assert response.status_code == 200
    
    async def test_disable_2fa_wrong_password(self, sync_client, admin_headers):
        """Désactivation 2FA avec mauvais mot de passe."""
        response = sync_client.post(
            "/api/v1/admin/2fa/disable",
            headers=admin_headers,
            json={"password": "WrongPassword123!"}
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAuthBackupCodes:
    """Tests des codes de secours (endpoint POST /api/v1/admin/2fa/backup-codes/regenerate)."""
    
    async def test_regenerate_backup_codes_success(self, sync_client, admin_headers):
        """Régénération des codes de secours réussie."""
        # First setup 2FA
        setup_resp = sync_client.post(
            "/api/v1/admin/2fa/enable",
            headers=admin_headers,
        )
        secret = setup_resp.json()["secret"]
        
        # Verify 2FA
        totp = pyotp.TOTP(secret)
        code = totp.now()
        sync_client.post(
            "/api/v1/admin/2fa/verify",
            headers=admin_headers,
            json={"two_factor_code": code}
        )
        
        # Regenerate backup codes
        response = sync_client.post(
            "/api/v1/admin/2fa/backup-codes/regenerate",
            headers=admin_headers,
            json={"password": "AdminTest123!"}
        )
        assert response.status_code == 200
        assert len(response.json()["backup_codes"]) == 10
