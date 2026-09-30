"""
Tests d'intégration pour la gestion des documents (knowledge base).
Couvre: upload, list, detail, delete, activiation.
"""

import pytest
from io import BytesIO
from uuid import uuid4
from app.models.domain.knowledge import KnowledgeDocument


@pytest.mark.asyncio
class TestKnowledgeUpload:
    """Tests d'upload de documents (endpoint POST /api/v1/admin/knowledge)."""
    
    async def test_upload_pdf_success(self, sync_client, admin_headers):
        """Upload d'un fichier PDF réussi."""
        file_content = b"%PDF-1.4\n% Test PDF content"
        
        response = sync_client.post(
            "/api/v1/admin/knowledge",
            headers={"Authorization": admin_headers.get("Authorization")},
            files={"file": ("test.pdf", BytesIO(file_content), "application/pdf")},
            data={
                "title": "Test Document",
                "is_active": "true"
            }
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert data["title"] == "Test Document"
        assert data["file_type"] == "pdf"
    
    async def test_upload_txt_success(self, sync_client, admin_headers):
        """Upload d'un fichier TXT réussi."""
        file_content = b"This is a test text file content."
        
        response = sync_client.post(
            "/api/v1/admin/knowledge",
            headers={"Authorization": admin_headers.get("Authorization")},
            files={"file": ("test.txt", BytesIO(file_content), "text/plain")},
            data={"title": "Text Document"}
        )
        assert response.status_code in [200, 201]
    
    async def test_upload_markdown_success(self, sync_client, admin_headers):
        """Upload d'un fichier Markdown réussi."""
        file_content = b"# Test Markdown\n\nThis is a test."
        
        response = sync_client.post(
            "/api/v1/admin/knowledge",
            headers={"Authorization": admin_headers.get("Authorization")},
            files={"file": ("test.md", BytesIO(file_content), "text/markdown")},
            data={"title": "Markdown Document"}
        )
        assert response.status_code in [200, 201]
    
    async def test_upload_invalid_file_type(self, sync_client, admin_headers):
        """Upload d'un fichier avec type invalide échoue."""
        file_content = b"Invalid file content"
        
        response = sync_client.post(
            "/api/v1/admin/knowledge",
            headers={"Authorization": admin_headers.get("Authorization")},
            files={"file": ("test.exe", BytesIO(file_content), "application/x-msdownload")},
            data={"title": "Invalid File"}
        )
        assert response.status_code in [400, 422]
    
    async def test_upload_path_traversal_prevention(self, sync_client, admin_headers):
        """Prévention de path traversal dans le nom de fichier."""
        file_content = b"Test content"
        
        # Attempt path traversal
        response = sync_client.post(
            "/api/v1/admin/knowledge",
            headers={"Authorization": admin_headers.get("Authorization")},
            files={"file": ("../../etc/passwd", BytesIO(file_content), "text/plain")},
            data={"title": "Malicious File"}
        )
        # Should sanitize the filename
        if response.status_code in [200, 201]:
            data = response.json()
            # Filename should be sanitized (no path separators)
            assert ".." not in data.get("filename", "")
            assert "/" not in data.get("filename", "")
    
    async def test_upload_empty_file(self, sync_client, admin_headers):
        """Upload d'un fichier vide échoue."""
        response = sync_client.post(
            "/api/v1/admin/knowledge",
            headers={"Authorization": admin_headers.get("Authorization")},
            files={"file": ("empty.pdf", BytesIO(b""), "application/pdf")},
            data={"title": "Empty File"}
        )
        assert response.status_code in [400, 422]
    
    async def test_upload_oversized_file(self, sync_client, admin_headers):
        """Upload d'un fichier trop volumineux échoue."""
        # Create a large file (>100MB)
        large_content = b"x" * (101 * 1024 * 1024)
        
        response = sync_client.post(
            "/api/v1/admin/knowledge",
            headers={"Authorization": admin_headers.get("Authorization")},
            files={"file": ("large.pdf", BytesIO(large_content), "application/pdf")},
            data={"title": "Large File"}
        )
        assert response.status_code in [413, 422]
    
    async def test_upload_requires_title(self, sync_client, admin_headers):
        """Upload sans titre échoue."""
        response = sync_client.post(
            "/api/v1/admin/knowledge",
            headers={"Authorization": admin_headers.get("Authorization")},
            files={"file": ("test.pdf", BytesIO(b"%PDF"), "application/pdf")},
            # Missing title
        )
        assert response.status_code == 422
    
    async def test_upload_requires_auth(self, sync_client):
        """Upload sans authentification échoue."""
        response = sync_client.post(
            "/api/v1/admin/knowledge",
            files={"file": ("test.pdf", BytesIO(b"%PDF"), "application/pdf")},
            data={"title": "Test"}
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestKnowledgeList:
    """Tests de liste des documents (endpoint GET /api/v1/admin/knowledge)."""
    
    async def test_list_documents_success(self, sync_client, admin_headers):
        """Liste des documents réussie."""
        response = sync_client.get(
            "/api/v1/admin/knowledge",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "total" in data
    
    async def test_list_documents_pagination(self, sync_client, admin_headers):
        """Liste des documents avec pagination."""
        response = sync_client.get(
            "/api/v1/admin/knowledge?limit=10&offset=0",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 0
    
    async def test_list_documents_filter_by_status(self, sync_client, admin_headers):
        """Liste des documents filtrée par statut actif."""
        response = sync_client.get(
            "/api/v1/admin/knowledge?is_active=true",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for doc in data["documents"]:
            assert doc["is_active"] is True
    
    async def test_list_documents_filter_by_type(self, sync_client, admin_headers):
        """Liste des documents filtrée par type."""
        response = sync_client.get(
            "/api/v1/admin/knowledge?file_type=pdf",
            headers=admin_headers,
        )
        assert response.status_code == 200
        # All documents should be PDFs (or empty list)
    
    async def test_list_documents_search(self, sync_client, admin_headers):
        """Recherche dans les documents."""
        response = sync_client.get(
            "/api/v1/admin/knowledge?search=test",
            headers=admin_headers,
        )
        assert response.status_code == 200
    
    async def test_list_documents_requires_auth(self, sync_client):
        """Liste des documents sans authentification échoue."""
        response = sync_client.get("/api/v1/admin/knowledge")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestKnowledgeDetail:
    """Tests de détail d'un document (endpoint GET /api/v1/admin/knowledge/{doc_id})."""
    
    async def test_get_document_success(self, sync_client, admin_headers, db_session, test_admin):
        """Récupération d'un document réussie."""
        # Create a test document
        doc = KnowledgeDocument(
            id=uuid4(),
            title="Test Document",
            filename="test.pdf",
            file_type="pdf",
            content="Test content",
            uploaded_by=test_admin.id,
            is_active=True,
            chunk_count=1,
        )
        db_session.add(doc)
        await db_session.commit()
        
        response = sync_client.get(
            f"/api/v1/admin/knowledge/{doc.id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(doc.id)
        assert data["title"] == "Test Document"
    
    async def test_get_document_not_found(self, sync_client, admin_headers):
        """Récupération d'un document inexistant."""
        response = sync_client.get(
            f"/api/v1/admin/knowledge/{uuid4()}",
            headers=admin_headers,
        )
        assert response.status_code == 404
    
    async def test_get_document_requires_auth(self, sync_client):
        """Récupération d'un document sans authentification échoue."""
        response = sync_client.get(
            f"/api/v1/admin/knowledge/{uuid4()}",
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestKnowledgeUpdate:
    """Tests de mise à jour d'un document (endpoint PUT /api/v1/admin/knowledge/{doc_id})."""
    
    async def test_update_document_success(self, sync_client, admin_headers, db_session, test_admin):
        """Mise à jour d'un document réussie."""
        # Create a test document
        doc = KnowledgeDocument(
            id=uuid4(),
            title="Original Title",
            filename="test.pdf",
            file_type="pdf",
            content="Test content",
            uploaded_by=test_admin.id,
            is_active=True,
        )
        db_session.add(doc)
        await db_session.commit()
        
        response = sync_client.put(
            f"/api/v1/admin/knowledge/{doc.id}",
            headers=admin_headers,
            json={
                "title": "Updated Title",
                "is_active": False,
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["is_active"] is False
    
    async def test_update_document_not_found(self, sync_client, admin_headers):
        """Mise à jour d'un document inexistant."""
        response = sync_client.put(
            f"/api/v1/admin/knowledge/{uuid4()}",
            headers=admin_headers,
            json={"title": "Updated Title"}
        )
        assert response.status_code == 404
    
    async def test_update_document_requires_auth(self, sync_client):
        """Mise à jour d'un document sans authentification échoue."""
        response = sync_client.put(
            f"/api/v1/admin/knowledge/{uuid4()}",
            json={"title": "Updated Title"}
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestKnowledgeDelete:
    """Tests de suppression d'un document (endpoint DELETE /api/v1/admin/knowledge/{doc_id})."""
    
    async def test_delete_document_success(self, sync_client, admin_headers, db_session, test_admin):
        """Suppression d'un document réussie."""
        # Create a test document
        doc = KnowledgeDocument(
            id=uuid4(),
            title="Document to Delete",
            filename="test.pdf",
            file_type="pdf",
            content="Test content",
            uploaded_by=test_admin.id,
            is_active=True,
        )
        db_session.add(doc)
        await db_session.commit()
        
        response = sync_client.delete(
            f"/api/v1/admin/knowledge/{doc.id}",
            headers=admin_headers,
        )
        assert response.status_code in [200, 204]
    
    async def test_delete_document_not_found(self, sync_client, admin_headers):
        """Suppression d'un document inexistant."""
        response = sync_client.delete(
            f"/api/v1/admin/knowledge/{uuid4()}",
            headers=admin_headers,
        )
        assert response.status_code == 404
    
    async def test_delete_document_requires_auth(self, sync_client):
        """Suppression d'un document sans authentification échoue."""
        response = sync_client.delete(
            f"/api/v1/admin/knowledge/{uuid4()}",
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestKnowledgeActivation:
    """Tests d'activation/désactivation de documents."""
    
    async def test_activate_document(self, sync_client, admin_headers, db_session, test_admin):
        """Activation d'un document."""
        doc = KnowledgeDocument(
            id=uuid4(),
            title="Inactive Document",
            filename="test.pdf",
            file_type="pdf",
            content="Test content",
            uploaded_by=test_admin.id,
            is_active=False,
        )
        db_session.add(doc)
        await db_session.commit()
        
        response = sync_client.put(
            f"/api/v1/admin/knowledge/{doc.id}",
            headers=admin_headers,
            json={"is_active": True}
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is True
    
    async def test_deactivate_document(self, sync_client, admin_headers, db_session, test_admin):
        """Désactivation d'un document."""
        doc = KnowledgeDocument(
            id=uuid4(),
            title="Active Document",
            filename="test.pdf",
            file_type="pdf",
            content="Test content",
            uploaded_by=test_admin.id,
            is_active=True,
        )
        db_session.add(doc)
        await db_session.commit()
        
        response = sync_client.put(
            f"/api/v1/admin/knowledge/{doc.id}",
            headers=admin_headers,
            json={"is_active": False}
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False


@pytest.mark.asyncio
class TestKnowledgeRBAC:
    """Tests des permissions RBAC pour la gestion des documents."""
    
    async def test_auditor_can_view_but_not_upload(self, sync_client, auditor_headers):
        """AUDITOR peut voir mais ne peut pas uploader."""
        # Can view
        response = sync_client.get(
            "/api/v1/admin/knowledge",
            headers=auditor_headers,
        )
        assert response.status_code == 200
        
        # Cannot upload
        response = sync_client.post(
            "/api/v1/admin/knowledge",
            headers={"Authorization": auditor_headers.get("Authorization")},
            files={"file": ("test.pdf", BytesIO(b"%PDF"), "application/pdf")},
            data={"title": "Test"}
        )
        assert response.status_code == 403
    
    async def test_viewer_can_only_view(self, sync_client, db_session):
        """VIEWER peut uniquement voir les documents."""
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
        
        # Can view
        response = sync_client.get(
            "/api/v1/admin/knowledge",
            headers=viewer_headers,
        )
        assert response.status_code == 200
        
        # Cannot modify
        response = sync_client.post(
            "/api/v1/admin/knowledge",
            headers={"Authorization": viewer_headers.get("Authorization")},
            files={"file": ("test.pdf", BytesIO(b"%PDF"), "application/pdf")},
            data={"title": "Test"}
        )
        assert response.status_code == 403
