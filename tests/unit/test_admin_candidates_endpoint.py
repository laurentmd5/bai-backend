"""
Unit tests for Admin Candidates Management endpoints (/api/v1/admin/candidates).
Tests listing, filtering, pagination, stats, CSV export, detail view, status updates, and deletions.
"""

from datetime import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import create_app
from app.api.dependencies.auth import get_current_admin
from app.api.v1.endpoints.admin.candidates import get_candidate_repository
from app.models.domain.candidate import CandidateApplication, ApplicationStatus
from app.repositories.candidate_repository import CandidateApplicationRepository


def dummy_candidate(
    candidate_id="cand_123",
    full_name="Abdoulaye Wade",
    phone="+221770001122",
    status=ApplicationStatus.PRESCREENED,
    match_score=80.0
):
    """Helper to generate a mock CandidateApplication instance."""
    return CandidateApplication(
        id=candidate_id,
        session_id="sess_123",
        channel="whatsapp",
        full_name=full_name,
        email="abdoulaye@example.sn",
        phone_number=phone,
        cv_filename="cv_abdoulaye.pdf",
        raw_cv_text="CV ingénieur réseaux",
        parsed_profile={"skills": ["Cisco", "Linux"]},
        answers_json={"q1": "Oui", "q2": "Immédiat"},
        match_score=match_score,
        target_domains=["Réseaux", "Télécom"],
        status=status,
        notes="Bon profil",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )


@pytest.fixture
def mock_repo():
    repo = MagicMock(spec=CandidateApplicationRepository)
    repo.list_applications = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.update_status = AsyncMock()
    repo.delete_application = AsyncMock()
    repo.get_stats = AsyncMock()
    return repo


@pytest.fixture
def app(mock_repo):
    test_app = create_app()
    # Mock admin auth dependency
    test_app.dependency_overrides[get_current_admin] = lambda: {
        "id": "admin_uuid_1",
        "email": "admin@company.com",
        "role": "admin"
    }
    # Mock candidate repository dependency
    test_app.dependency_overrides[get_candidate_repository] = lambda: mock_repo
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


CSRF_HEADERS = {"X-CSRF-Token": "test_csrf_token_123"}
CSRF_COOKIES = {"csrf_token": "test_csrf_token_123"}


class TestAdminCandidatesEndpoints:
    """Test suite for /api/v1/admin/candidates endpoints."""

    def test_unauthenticated_request_rejected(self):
        """Requests without authentication must receive 401."""
        raw_app = create_app()
        from app.api.dependencies.auth import get_admin_service
        raw_app.dependency_overrides[get_admin_service] = lambda: MagicMock()
        raw_client = TestClient(raw_app)
        response = raw_client.get("/api/v1/admin/candidates")
        assert response.status_code == 401

    def test_list_candidates_success(self, client, mock_repo):
        """Should list candidate applications with pagination info."""
        cand = dummy_candidate()
        mock_repo.list_applications.return_value = ([cand], 1)

        response = client.get("/api/v1/admin/candidates?limit=20&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["limit"] == 20
        assert data["offset"] == 0
        assert len(data["candidates"]) == 1
        assert data["candidates"][0]["full_name"] == "Abdoulaye Wade"
        assert data["candidates"][0]["match_score"] == 80.0

    def test_list_candidates_with_filters(self, client, mock_repo):
        """Should pass filter arguments to the repository."""
        mock_repo.list_applications.return_value = ([], 0)

        response = client.get(
            "/api/v1/admin/candidates?status=shortlisted&channel=whatsapp&min_score=75&search=Abdoulaye"
        )
        assert response.status_code == 200
        mock_repo.list_applications.assert_called_once_with(
            limit=50,
            offset=0,
            status=ApplicationStatus.SHORTLISTED,
            channel="whatsapp",
            min_score=75.0,
            search="Abdoulaye",
            sort_by="created_at",
            sort_order="desc"
        )

    def test_get_candidates_stats(self, client, mock_repo):
        """Should return aggregated dashboard statistics."""
        mock_repo.get_stats.return_value = {
            "total_applications": 25,
            "by_status": {"prescreened": 15, "shortlisted": 5, "rejected": 5},
            "by_channel": {"whatsapp": 20, "web": 5},
            "avg_match_score": 78.4,
            "with_cv_count": 18
        }

        response = client.get("/api/v1/admin/candidates/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_applications"] == 25
        assert data["by_status"]["prescreened"] == 15
        assert data["avg_match_score"] == 78.4
        assert data["with_cv_count"] == 18

    def test_export_candidates_csv(self, client, mock_repo):
        """Should return downloadable CSV file with correct headers and content."""
        cand = dummy_candidate(full_name="Aminata Ndiaye", match_score=92.0)
        mock_repo.list_applications.return_value = ([cand], 1)

        response = client.get("/api/v1/admin/candidates/export/csv")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment; filename=candidatures_export.csv" in response.headers["content-disposition"]
        content = response.content.decode("utf-8-sig")
        assert "Nom Complet" in content
        assert "Aminata Ndiaye" in content
        assert "92.0" in content

    def test_get_candidate_detail_found(self, client, mock_repo):
        """Should return full candidate details when application exists."""
        cand = dummy_candidate(candidate_id="uuid-456")
        mock_repo.get_by_id.return_value = cand

        response = client.get("/api/v1/admin/candidates/uuid-456")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "uuid-456"
        assert data["cv_filename"] == "cv_abdoulaye.pdf"
        assert data["answers_json"]["q1"] == "Oui"

    def test_get_candidate_detail_not_found(self, client, mock_repo):
        """Should return 404 when candidate ID does not exist."""
        mock_repo.get_by_id.return_value = None

        response = client.get("/api/v1/admin/candidates/non-existent-uuid")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_update_candidate_status_success(self, client, mock_repo):
        """Should update application status and recruiter notes."""
        cand = dummy_candidate(candidate_id="uuid-789", status=ApplicationStatus.SHORTLISTED)
        cand.notes = "Candidat sélectionné pour entretien technique"
        mock_repo.update_status.return_value = cand

        payload = {
            "status": "shortlisted",
            "notes": "Candidat sélectionné pour entretien technique"
        }
        response = client.patch(
            "/api/v1/admin/candidates/uuid-789/status",
            json=payload,
            headers=CSRF_HEADERS,
            cookies=CSRF_COOKIES
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "shortlisted"
        assert data["notes"] == "Candidat sélectionné pour entretien technique"
        mock_repo.update_status.assert_called_once_with(
            application_id="uuid-789",
            status=ApplicationStatus.SHORTLISTED,
            notes="Candidat sélectionné pour entretien technique"
        )

    def test_update_candidate_status_not_found(self, client, mock_repo):
        """Should return 404 when updating non-existent candidate."""
        mock_repo.update_status.return_value = None

        payload = {"status": "rejected", "notes": "Injoignable"}
        response = client.patch(
            "/api/v1/admin/candidates/unknown-id/status",
            json=payload,
            headers=CSRF_HEADERS,
            cookies=CSRF_COOKIES
        )
        assert response.status_code == 404

    def test_delete_candidate_success(self, client, mock_repo):
        """Should delete application and return confirmation."""
        mock_repo.delete_application.return_value = True

        response = client.delete(
            "/api/v1/admin/candidates/cand_to_delete",
            headers=CSRF_HEADERS,
            cookies=CSRF_COOKIES
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_repo.delete_application.assert_called_once_with("cand_to_delete")

    def test_delete_candidate_not_found(self, client, mock_repo):
        """Should return 404 when deleting non-existent application."""
        mock_repo.delete_application.return_value = False

        response = client.delete(
            "/api/v1/admin/candidates/unknown-cand",
            headers=CSRF_HEADERS,
            cookies=CSRF_COOKIES
        )
        assert response.status_code == 404
