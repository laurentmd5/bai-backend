"""
Tests d'intégration pour les endpoints de gestion des utilisateurs.
Couvre: CRUD utilisateurs, list, filtrage, permissions.
"""

import pytest
from uuid import uuid4
from app.models.domain.admin import AdminUser
from app.core.security import hash_password


@pytest.mark.asyncio
class TestUsersCreate:
    """Tests de création d'utilisateurs (endpoint POST /api/v1/admin/users)."""
    
    async def test_create_user_success(self, sync_client, admin_headers):
        """Création d'utilisateur réussie."""
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "email": "newuser@test.com",
                "password": "NewUser123!",
                "full_name": "New User",
                "role": "ADMIN",
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@test.com"
        assert data["role"] == "ADMIN"
        assert "id" in data
    
    async def test_create_user_duplicate_email(self, sync_client, test_admin, admin_headers):
        """Création d'utilisateur avec email déjà existant."""
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "email": test_admin.email,  # Already exists
                "password": "Password123!",
                "full_name": "Another User",
                "role": "ADMIN",
            }
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()
    
    async def test_create_user_weak_password(self, sync_client, admin_headers):
        """Création d'utilisateur avec mot de passe faible."""
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "email": "weak@test.com",
                "password": "123",  # Too weak
                "full_name": "Weak User",
                "role": "ADMIN",
            }
        )
        assert response.status_code == 422
    
    async def test_create_user_invalid_email(self, sync_client, admin_headers):
        """Création d'utilisateur avec email invalide."""
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "email": "not-an-email",
                "password": "Password123!",
                "full_name": "Invalid Email",
                "role": "ADMIN",
            }
        )
        assert response.status_code == 422
    
    async def test_create_user_missing_fields(self, sync_client, admin_headers):
        """Création d'utilisateur avec champs manquants."""
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "email": "test@test.com",
                # Missing password, full_name, role
            }
        )
        assert response.status_code == 422
    
    async def test_create_user_invalid_role(self, sync_client, admin_headers):
        """Création d'utilisateur avec rôle invalide."""
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "email": "newuser@test.com",
                "password": "Password123!",
                "full_name": "New User",
                "role": "INVALID_ROLE",
            }
        )
        assert response.status_code == 422
    
    async def test_create_user_requires_admin(self, sync_client, auditor_headers):
        """Création d'utilisateur avec rôle AUDITOR échoue."""
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=auditor_headers,
            json={
                "email": "newuser@test.com",
                "password": "Password123!",
                "full_name": "New User",
                "role": "ADMIN",
            }
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestUsersRead:
    """Tests de lecture d'utilisateurs (endpoint GET /api/v1/admin/users/{user_id})."""
    
    async def test_get_user_success(self, sync_client, test_admin, admin_headers):
        """Lecture d'utilisateur réussie."""
        response = sync_client.get(
            f"/api/v1/admin/users/{test_admin.id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_admin.email
        assert data["id"] == str(test_admin.id)
    
    async def test_get_user_not_found(self, sync_client, admin_headers):
        """Lecture d'utilisateur inexistant."""
        response = sync_client.get(
            f"/api/v1/admin/users/{uuid4()}",
            headers=admin_headers,
        )
        assert response.status_code == 404
    
    async def test_get_user_invalid_uuid(self, sync_client, admin_headers):
        """Lecture d'utilisateur avec UUID invalide."""
        response = sync_client.get(
            "/api/v1/admin/users/invalid-uuid",
            headers=admin_headers,
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestUsersList:
    """Tests de liste des utilisateurs (endpoint GET /api/v1/admin/users)."""
    
    async def test_list_users_success(self, sync_client, test_admin, test_regular_admin, test_auditor, admin_headers):
        """Liste d'utilisateurs réussie."""
        response = sync_client.get(
            "/api/v1/admin/users",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "total" in data
        assert len(data["users"]) > 0
    
    async def test_list_users_pagination(self, sync_client, admin_headers):
        """Liste d'utilisateurs avec pagination."""
        response = sync_client.get(
            "/api/v1/admin/users?limit=10&offset=0",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 0
    
    async def test_list_users_filter_by_role(self, sync_client, admin_headers):
        """Liste d'utilisateurs filtrée par rôle."""
        response = sync_client.get(
            "/api/v1/admin/users?role=ADMIN",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for user in data["users"]:
            assert user["role"] == "ADMIN"
    
    async def test_list_users_filter_by_active(self, sync_client, admin_headers):
        """Liste d'utilisateurs filtrée par statut actif."""
        response = sync_client.get(
            "/api/v1/admin/users?is_active=true",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for user in data["users"]:
            assert user["is_active"] is True


@pytest.mark.asyncio
class TestUsersUpdate:
    """Tests de mise à jour d'utilisateurs (endpoint PUT /api/v1/admin/users/{user_id})."""
    
    async def test_update_user_success(self, sync_client, test_regular_admin, admin_headers):
        """Mise à jour d'utilisateur réussie."""
        response = sync_client.put(
            f"/api/v1/admin/users/{test_regular_admin.id}",
            headers=admin_headers,
            json={
                "full_name": "Updated Name",
                "role": "AUDITOR",
                "is_active": True,
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Updated Name"
        assert data["role"] == "AUDITOR"
    
    async def test_update_user_not_found(self, sync_client, admin_headers):
        """Mise à jour d'utilisateur inexistant."""
        response = sync_client.put(
            f"/api/v1/admin/users/{uuid4()}",
            headers=admin_headers,
            json={
                "full_name": "Updated Name",
            }
        )
        assert response.status_code == 404
    
    async def test_update_user_deactivate(self, sync_client, test_regular_admin, admin_headers):
        """Désactivation d'utilisateur."""
        response = sync_client.put(
            f"/api/v1/admin/users/{test_regular_admin.id}",
            headers=admin_headers,
            json={
                "is_active": False,
            }
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False
    
    async def test_update_user_cannot_update_email(self, sync_client, test_regular_admin, admin_headers):
        """Mise à jour de l'email échoue (email ne peut pas être changé)."""
        response = sync_client.put(
            f"/api/v1/admin/users/{test_regular_admin.id}",
            headers=admin_headers,
            json={
                "email": "newemail@test.com",  # Should be ignored or fail
            }
        )
        # Email should not be updated
        if response.status_code == 200:
            assert response.json()["email"] == test_regular_admin.email


@pytest.mark.asyncio
class TestUsersDelete:
    """Tests de suppression d'utilisateurs (endpoint DELETE /api/v1/admin/users/{user_id})."""
    
    async def test_delete_user_success(self, sync_client, test_regular_admin, admin_headers):
        """Suppression d'utilisateur réussie (soft delete)."""
        response = sync_client.delete(
            f"/api/v1/admin/users/{test_regular_admin.id}",
            headers=admin_headers,
        )
        assert response.status_code == 204 or response.status_code == 200
    
    async def test_delete_user_not_found(self, sync_client, admin_headers):
        """Suppression d'utilisateur inexistant."""
        response = sync_client.delete(
            f"/api/v1/admin/users/{uuid4()}",
            headers=admin_headers,
        )
        assert response.status_code == 404
    
    async def test_delete_user_cannot_delete_self(self, sync_client, test_admin, admin_headers):
        """Suppression du propre compte échoue."""
        response = sync_client.delete(
            f"/api/v1/admin/users/{test_admin.id}",
            headers=admin_headers,
        )
        # Should fail to prevent self-deletion
        assert response.status_code in [400, 403, 409]
    
    async def test_delete_user_requires_admin(self, sync_client, test_regular_admin, auditor_headers):
        """Suppression d'utilisateur avec rôle AUDITOR échoue."""
        response = sync_client.delete(
            f"/api/v1/admin/users/{test_regular_admin.id}",
            headers=auditor_headers,
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestUsersRBAC:
    """Tests des permissions RBAC pour les utilisateurs."""
    
    async def test_superadmin_can_manage_all_roles(self, sync_client, admin_headers):
        """SUPERADMIN peut créer des utilisateurs de tous les rôles."""
        for role in ["SUPERADMIN", "ADMIN", "AUDITOR", "VIEWER"]:
            response = sync_client.post(
                "/api/v1/admin/users",
                headers=admin_headers,
                json={
                    "email": f"user_{role}@test.com",
                    "password": "Password123!",
                    "full_name": f"User {role}",
                    "role": role,
                }
            )
            assert response.status_code == 201
    
    async def test_admin_cannot_create_superadmin(self, sync_client, regular_admin_headers):
        """ADMIN ne peut pas créer un SUPERADMIN."""
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=regular_admin_headers,
            json={
                "email": "superadmin@test.com",
                "password": "Password123!",
                "full_name": "Super Admin",
                "role": "SUPERADMIN",
            }
        )
        assert response.status_code == 403
    
    async def test_auditor_cannot_create_users(self, sync_client, auditor_headers):
        """AUDITOR ne peut pas créer d'utilisateurs."""
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=auditor_headers,
            json={
                "email": "newuser@test.com",
                "password": "Password123!",
                "full_name": "New User",
                "role": "VIEWER",
            }
        )
        assert response.status_code == 403
    
    async def test_viewer_cannot_create_users(self, sync_client):
        """VIEWER ne peut pas créer d'utilisateurs."""
        viewer_token = create_jwt_token(
            {
                "sub": str(uuid4()),
                "email": "viewer@test.com",
                "role": "VIEWER",
            },
            "access"
        )
        response = sync_client.post(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "email": "newuser@test.com",
                "password": "Password123!",
                "full_name": "New User",
                "role": "VIEWER",
            }
        )
        assert response.status_code == 403
    
    async def test_auditor_can_view_users_but_not_modify(self, sync_client, test_regular_admin, auditor_headers):
        """AUDITOR peut voir les utilisateurs mais ne peut pas les modifier."""
        # Can view
        response = sync_client.get(
            "/api/v1/admin/users",
            headers=auditor_headers,
        )
        assert response.status_code == 200
        
        # Cannot modify
        response = sync_client.put(
            f"/api/v1/admin/users/{test_regular_admin.id}",
            headers=auditor_headers,
            json={"full_name": "Modified"}
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestUsersValidation:
    """Tests de validation des données utilisateurs."""
    
    async def test_email_validation_format(self, sync_client, admin_headers):
        """Validation du format email."""
        invalid_emails = [
            "notanemail",
            "missing@domain",
            "@nodomain.com",
            "spaces in@email.com",
        ]
        for email in invalid_emails:
            response = sync_client.post(
                "/api/v1/admin/users",
                headers=admin_headers,
                json={
                    "email": email,
                    "password": "Password123!",
                    "full_name": "Test User",
                    "role": "ADMIN",
                }
            )
            assert response.status_code in [422, 400]
    
    async def test_password_strength_validation(self, sync_client, admin_headers):
        """Validation de la force du mot de passe."""
        weak_passwords = [
            "123456",  # Numbers only
            "abcdef",  # Letters only
            "Abc123",  # Too short
            "password",  # No numbers/special chars
        ]
        for password in weak_passwords:
            response = sync_client.post(
                "/api/v1/admin/users",
                headers=admin_headers,
                json={
                    "email": f"user_{password[:5]}@test.com",
                    "password": password,
                    "full_name": "Test User",
                    "role": "ADMIN",
                }
            )
            assert response.status_code == 422
    
    async def test_name_length_validation(self, sync_client, admin_headers):
        """Validation de la longueur du nom."""
        # Too long name (>100 chars)
        long_name = "A" * 101
        response = sync_client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "email": "user@test.com",
                "password": "Password123!",
                "full_name": long_name,
                "role": "ADMIN",
            }
        )
        assert response.status_code == 422


# Helper function for RBAC test
from app.core.security import create_jwt_token
