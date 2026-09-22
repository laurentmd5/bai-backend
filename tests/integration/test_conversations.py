"""
Tests d'intégration pour les conversations et audit logs.
Couvre: conversations list/detail, audit logs, statistiques.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from app.models.domain.conversation import Conversation
from app.models.domain.session import Session
from app.models.domain.admin import AuditLog


@pytest.mark.asyncio
class TestConversationsList:
    """Tests de liste des conversations (endpoint GET /api/v1/admin/conversations)."""
    
    async def test_list_conversations_success(self, sync_client, admin_headers):
        """Liste des conversations réussie."""
        response = sync_client.get(
            "/api/v1/admin/conversations",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data
        assert "total" in data
    
    async def test_list_conversations_pagination(self, sync_client, admin_headers):
        """Liste des conversations avec pagination."""
        response = sync_client.get(
            "/api/v1/admin/conversations?limit=15&offset=0",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 15
        assert data["offset"] == 0
    
    async def test_list_conversations_filter_by_channel(self, sync_client, admin_headers):
        """Filtrage des conversations par canal."""
        response = sync_client.get(
            "/api/v1/admin/conversations?channel=web",
            headers=admin_headers,
        )
        assert response.status_code == 200
        # All conversations should be from web channel
    
    async def test_list_conversations_filter_by_date_range(self, sync_client, admin_headers):
        """Filtrage des conversations par plage de dates."""
        start_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
        end_date = datetime.utcnow().isoformat()
        
        response = sync_client.get(
            f"/api/v1/admin/conversations?start_date={start_date}&end_date={end_date}",
            headers=admin_headers,
        )
        assert response.status_code == 200
    
    async def test_list_conversations_filter_by_feedback(self, sync_client, admin_headers):
        """Filtrage des conversations par feedback."""
        response = sync_client.get(
            "/api/v1/admin/conversations?feedback=positive",
            headers=admin_headers,
        )
        assert response.status_code == 200
    
    async def test_list_conversations_requires_auth(self, sync_client):
        """Liste des conversations sans authentification échoue."""
        response = sync_client.get("/api/v1/admin/conversations")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestConversationDetail:
    """Tests de détail d'une conversation (endpoint GET /api/v1/admin/conversations/{conv_id})."""
    
    async def test_get_conversation_success(self, sync_client, admin_headers, db_session):
        """Récupération d'une conversation réussie."""
        # Create test session and conversation
        session = Session(
            id=uuid4(),
            user_id="test_user",
            channel="web",
        )
        db_session.add(session)
        await db_session.commit()
        
        conv = Conversation(
            id=uuid4(),
            session_id=session.id,
            user_message="What is NPP?",
            bot_response="NPP is the National People's Party...",
            confidence=0.95,
            channel="web",
        )
        db_session.add(conv)
        await db_session.commit()
        
        response = sync_client.get(
            f"/api/v1/admin/conversations/{conv.id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_message"] == "What is NPP?"
        assert data["confidence"] == 0.95
    
    async def test_get_conversation_not_found(self, sync_client, admin_headers):
        """Récupération d'une conversation inexistante."""
        response = sync_client.get(
            f"/api/v1/admin/conversations/{uuid4()}",
            headers=admin_headers,
        )
        assert response.status_code == 404
    
    async def test_get_conversation_with_sources(self, sync_client, admin_headers, db_session):
        """Récupération d'une conversation avec sources."""
        session = Session(
            id=uuid4(),
            user_id="test_user",
            channel="web",
        )
        db_session.add(session)
        await db_session.commit()
        
        conv = Conversation(
            id=uuid4(),
            session_id=session.id,
            user_message="Tell me about policies",
            bot_response="Here are the policies...",
            confidence=0.87,
            channel="web",
            sources=[
                {"doc_id": str(uuid4()), "section": "Introduction", "relevance": 0.95},
                {"doc_id": str(uuid4()), "section": "Overview", "relevance": 0.85},
            ]
        )
        db_session.add(conv)
        await db_session.commit()
        
        response = sync_client.get(
            f"/api/v1/admin/conversations/{conv.id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("sources", [])) > 0


@pytest.mark.asyncio
class TestConversationBySession:
    """Tests pour récupérer les conversations d'une session (endpoint GET /api/v1/admin/conversations/session/{session_id})."""
    
    async def test_get_conversations_by_session(self, sync_client, admin_headers, db_session):
        """Récupération des conversations d'une session."""
        session = Session(
            id=uuid4(),
            user_id="test_user",
            channel="web",
        )
        db_session.add(session)
        await db_session.commit()
        
        # Create multiple conversations in session
        for i in range(3):
            conv = Conversation(
                id=uuid4(),
                session_id=session.id,
                user_message=f"Question {i}?",
                bot_response=f"Answer {i}",
                channel="web",
            )
            db_session.add(conv)
        await db_session.commit()
        
        response = sync_client.get(
            f"/api/v1/admin/conversations/session/{session.id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("conversations", [])) == 3


@pytest.mark.asyncio
class TestConversationDelete:
    """Tests de suppression de conversations (endpoint DELETE /api/v1/admin/conversations/{conv_id})."""
    
    async def test_delete_conversation_success(self, sync_client, admin_headers, db_session):
        """Suppression d'une conversation réussie."""
        session = Session(
            id=uuid4(),
            user_id="test_user",
            channel="web",
        )
        db_session.add(session)
        await db_session.commit()
        
        conv = Conversation(
            id=uuid4(),
            session_id=session.id,
            user_message="Test",
            bot_response="Test response",
        )
        db_session.add(conv)
        await db_session.commit()
        
        response = sync_client.delete(
            f"/api/v1/admin/conversations/{conv.id}",
            headers=admin_headers,
        )
        assert response.status_code in [200, 204]
    
    async def test_delete_conversation_requires_admin(self, sync_client, auditor_headers):
        """Suppression d'une conversation ne fonctionne pas pour AUDITOR."""
        response = sync_client.delete(
            f"/api/v1/admin/conversations/{uuid4()}",
            headers=auditor_headers,
        )
        # AUDITOR shouldn't be able to delete
        assert response.status_code == 403


@pytest.mark.asyncio
class TestAuditLogsList:
    """Tests de liste des audit logs (endpoint GET /api/v1/admin/audit)."""
    
    async def test_list_audit_logs_success(self, sync_client, admin_headers):
        """Liste des audit logs réussie."""
        response = sync_client.get(
            "/api/v1/admin/audit",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "total" in data
    
    async def test_list_audit_logs_pagination(self, sync_client, admin_headers):
        """Liste des audit logs avec pagination."""
        response = sync_client.get(
            "/api/v1/admin/audit?limit=20&offset=0",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 20
    
    async def test_list_audit_logs_filter_by_admin(self, sync_client, admin_headers, test_admin):
        """Filtrage des audit logs par admin."""
        response = sync_client.get(
            f"/api/v1/admin/audit?admin_id={test_admin.id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
    
    async def test_list_audit_logs_filter_by_severity(self, sync_client, admin_headers):
        """Filtrage des audit logs par sévérité."""
        for severity in ["INFO", "WARNING", "CRITICAL"]:
            response = sync_client.get(
                f"/api/v1/admin/audit?severity={severity}",
                headers=admin_headers,
            )
            assert response.status_code == 200
    
    async def test_list_audit_logs_filter_by_action(self, sync_client, admin_headers):
        """Filtrage des audit logs par action."""
        response = sync_client.get(
            "/api/v1/admin/audit?action=LOGIN_SUCCESS",
            headers=admin_headers,
        )
        assert response.status_code == 200
    
    async def test_list_audit_logs_requires_auth(self, sync_client):
        """Liste des audit logs sans authentification échoue."""
        response = sync_client.get("/api/v1/admin/audit")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAuditLogDetail:
    """Tests de détail d'un audit log (endpoint GET /api/v1/admin/audit/{log_id})."""
    
    async def test_get_audit_log_success(self, sync_client, admin_headers, db_session, test_admin):
        """Récupération d'un audit log réussi."""
        log = AuditLog(
            id=uuid4(),
            admin_id=test_admin.id,
            action="LOGIN_SUCCESS",
            resource_type="admin",
            resource_id=str(test_admin.id),
            severity="INFO",
            ip_address="127.0.0.1",
            user_agent="Test Agent",
        )
        db_session.add(log)
        await db_session.commit()
        
        response = sync_client.get(
            f"/api/v1/admin/audit/{log.id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "LOGIN_SUCCESS"
        assert data["severity"] == "INFO"
    
    async def test_get_audit_log_not_found(self, sync_client, admin_headers):
        """Récupération d'un audit log inexistant."""
        response = sync_client.get(
            f"/api/v1/admin/audit/{uuid4()}",
            headers=admin_headers,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestAuditByUser:
    """Tests pour récupérer les audit logs d'un utilisateur (endpoint GET /api/v1/admin/audit/user/{user_id})."""
    
    async def test_get_audit_by_user(self, sync_client, admin_headers, db_session, test_admin, test_regular_admin):
        """Récupération des audit logs par utilisateur."""
        # Create logs for test_admin
        for i in range(3):
            log = AuditLog(
                id=uuid4(),
                admin_id=test_admin.id,
                action="LOGIN_SUCCESS",
                resource_type="admin",
                resource_id=str(test_admin.id),
                severity="INFO",
            )
            db_session.add(log)
        await db_session.commit()
        
        response = sync_client.get(
            f"/api/v1/admin/audit/user/{test_admin.id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("logs", [])) >= 3


@pytest.mark.asyncio
class TestAuditDelete:
    """Tests de suppression d'audit logs (endpoint DELETE /api/v1/admin/audit/{log_id})."""
    
    async def test_delete_audit_log_superadmin_only(self, sync_client, admin_headers, db_session, test_admin):
        """Suppression d'un audit log - SUPERADMIN seulement."""
        log = AuditLog(
            id=uuid4(),
            admin_id=test_admin.id,
            action="LOGIN_SUCCESS",
            resource_type="admin",
            resource_id=str(test_admin.id),
            severity="INFO",
        )
        db_session.add(log)
        await db_session.commit()
        
        response = sync_client.delete(
            f"/api/v1/admin/audit/{log.id}",
            headers=admin_headers,
        )
        # SUPERADMIN should be able to delete
        assert response.status_code in [200, 204]
    
    async def test_delete_audit_log_admin_fails(self, sync_client, regular_admin_headers):
        """Suppression d'un audit log par ADMIN échoue."""
        response = sync_client.delete(
            f"/api/v1/admin/audit/{uuid4()}",
            headers=regular_admin_headers,
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestAuditRBAC:
    """Tests des permissions RBAC pour les audit logs."""
    
    async def test_auditor_can_view_all_logs(self, sync_client, auditor_headers):
        """AUDITOR peut voir tous les audit logs."""
        response = sync_client.get(
            "/api/v1/admin/audit",
            headers=auditor_headers,
        )
        assert response.status_code == 200
    
    async def test_auditor_cannot_delete_logs(self, sync_client, auditor_headers):
        """AUDITOR ne peut pas supprimer les logs."""
        response = sync_client.delete(
            f"/api/v1/admin/audit/{uuid4()}",
            headers=auditor_headers,
        )
        assert response.status_code == 403
    
    async def test_viewer_cannot_view_audit_logs(self, sync_client, db_session):
        """VIEWER ne peut pas accéder aux audit logs."""
        from app.core.security import create_jwt_token
        viewer_token = create_jwt_token(
            {
                "sub": str(uuid4()),
                "email": "viewer@test.com",
                "role": "VIEWER",
            },
            "access"
        )
        viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
        
        response = sync_client.get(
            "/api/v1/admin/audit",
            headers=viewer_headers,
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestConversationFeedback:
    """Tests du feedback sur les conversations."""
    
    async def test_submit_feedback_positive(self, sync_client, admin_headers, db_session):
        """Soumission d'un feedback positif."""
        session = Session(
            id=uuid4(),
            user_id="test_user",
            channel="web",
        )
        db_session.add(session)
        await db_session.commit()
        
        conv = Conversation(
            id=uuid4(),
            session_id=session.id,
            user_message="Test",
            bot_response="Response",
        )
        db_session.add(conv)
        await db_session.commit()
        
        response = sync_client.put(
            f"/api/v1/admin/conversations/{conv.id}/feedback",
            headers=admin_headers,
            json={"feedback": 1}  # positive
        )
        assert response.status_code == 200
    
    async def test_submit_feedback_negative(self, sync_client, admin_headers, db_session):
        """Soumission d'un feedback négatif."""
        session = Session(
            id=uuid4(),
            user_id="test_user",
            channel="web",
        )
        db_session.add(session)
        await db_session.commit()
        
        conv = Conversation(
            id=uuid4(),
            session_id=session.id,
            user_message="Test",
            bot_response="Response",
        )
        db_session.add(conv)
        await db_session.commit()
        
        response = sync_client.put(
            f"/api/v1/admin/conversations/{conv.id}/feedback",
            headers=admin_headers,
            json={"feedback": -1}  # negative
        )
        assert response.status_code == 200
