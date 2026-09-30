"""
Unit tests for CandidateApplication PostgreSQL persistence and EmailNotificationService.
Tests white-label configuration, email building, graceful skip, and end-to-end recruitment completion.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import SecretStr

from app.core.config import settings
from app.services.notification.email_service import EmailNotificationService, email_service
from app.services.recruitment.recruiter_agent import recruiter_agent, SCREENING_QUESTIONS
from app.repositories.candidate_repository import CandidateApplicationRepository
from app.models.domain.candidate import CandidateApplication, ApplicationStatus


class TestEmailNotificationService:
    """Test suite for EmailNotificationService."""

    def test_is_configured_false_by_default(self):
        """Should return False if notification email or SMTP creds are missing."""
        service = EmailNotificationService()
        with patch.object(settings, "RECRUITER_NOTIFICATION_EMAIL", None):
            assert service.is_configured is False

        with patch.object(settings, "RECRUITER_NOTIFICATION_EMAIL", "recruiter@example.com"):
            with patch.object(settings, "SMTP_USER", None):
                assert service.is_configured is False

    def test_is_configured_true_when_all_present(self):
        """Should return True when recipient, user, and password are provided."""
        service = EmailNotificationService()
        with patch.object(settings, "RECRUITER_NOTIFICATION_EMAIL", "recruiter@example.com"):
            with patch.object(settings, "SMTP_USER", "sender@example.com"):
                with patch.object(settings, "SMTP_PASSWORD", SecretStr("app-secret-pwd")):
                    assert service.is_configured is True

    @pytest.mark.asyncio
    async def test_send_skipped_when_not_configured(self):
        """Should return False and not raise when unconfigured."""
        service = EmailNotificationService()
        with patch.object(settings, "RECRUITER_NOTIFICATION_EMAIL", None):
            res = await service.send_recruitment_notification(
                full_name="Jean Dupont",
                phone_number="+221770000000",
                answers={"q1": "Oui"}
            )
            assert res is False

    def test_build_email_message_structure(self):
        """Should construct multipart email with plaintext and HTML containing candidate info."""
        service = EmailNotificationService()
        with patch.object(settings, "APP_NAME", "RecruitAI"):
            with patch.object(settings, "COMPANY_NAME", "TechCorp"):
                with patch.object(settings, "SMTP_FROM", "recrutement@techcorp.com"):
                    msg = service._build_email_message(
                        recipient_email="hr@techcorp.com",
                        full_name="Fatou Ndiaye",
                        phone_number="+221771234567",
                        email="fatou@gmail.com",
                        channel="whatsapp",
                        answers={
                            "q1_offer_knowledge": "Oui, tout à fait d'accord",
                            "q2_availability": "Immédiate",
                        },
                        cv_info={"filename": "cv_fatou.pdf", "summary": "Développeur Python FastAPI"},
                        match_score=85.0,
                        target_domains=["Développement Web", "FastAPI"]
                    )

                    assert msg["Subject"] == "[RecruitAI] Nouvelle Candidature : Fatou Ndiaye (WHATSAPP)"
                    assert msg["From"] == "recrutement@techcorp.com"
                    assert msg["To"] == "hr@techcorp.com"

                    payloads = [part.get_payload(decode=True).decode("utf-8") for part in msg.get_payload()]
                    assert len(payloads) == 2  # text, html

                    # Plaintext checks
                    assert "Fatou Ndiaye" in payloads[0]
                    assert "+221771234567" in payloads[0]
                    assert "TechCorp" in payloads[0]
                    assert "cv_fatou.pdf" in payloads[0]

                    # HTML checks
                    assert "Fatou Ndiaye" in payloads[1]
                    assert "85.0%" in payloads[1]
                    assert "TechCorp" in payloads[1]

    @pytest.mark.asyncio
    async def test_send_recruitment_notification_success(self):
        """Should successfully call smtplib when credentials provided."""
        service = EmailNotificationService()
        with patch.object(settings, "RECRUITER_NOTIFICATION_EMAIL", "hr@techcorp.com"):
            with patch.object(settings, "SMTP_USER", "bot@techcorp.com"):
                with patch.object(settings, "SMTP_PASSWORD", SecretStr("secret-app-token")):
                    with patch.object(service, "_send_sync", return_value=True) as mock_send_sync:
                        success = await service.send_recruitment_notification(
                            full_name="Moussa Ba",
                            phone_number="+221778889900",
                            channel="whatsapp",
                            answers={"q1": "Oui"}
                        )
                        assert success is True
                        assert mock_send_sync.called


class TestCandidateApplicationRepository:
    """Test suite for CandidateApplicationRepository."""

    @pytest.mark.asyncio
    async def test_save_application_new(self):
        """Should create a new CandidateApplication in database."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = CandidateApplicationRepository(session=mock_session)
        
        app = await repo.save_application(
            full_name="Ousmane Diallo",
            phone_number="+221776543210",
            email="ousmane@example.com",
            session_id="session_test_999",
            channel="whatsapp",
            answers={"q1_offer_knowledge": "Oui", "q2_availability": "Demain"},
            match_score=90.0,
            target_domains=["Réseaux", "Télécom"]
        )

        assert app.full_name == "Ousmane Diallo"
        assert app.phone_number == "+221776543210"
        assert app.session_id == "session_test_999"
        assert app.match_score == 90.0
        assert app.status == ApplicationStatus.PRESCREENED
        assert mock_session.add.called
        assert mock_session.flush.called

    @pytest.mark.asyncio
    async def test_save_application_update_existing(self):
        """Should update an existing CandidateApplication if session already exists."""
        existing_app = CandidateApplication(
            id="existing-id-123",
            session_id="session_test_999",
            full_name="Ousmane Initial",
            phone_number="+221776543210",
            answers_json={"q1": "Non"},
            match_score=50.0,
            status=ApplicationStatus.NEW
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_app
        mock_session.execute.return_value = mock_result

        repo = CandidateApplicationRepository(session=mock_session)

        updated = await repo.save_application(
            full_name="Ousmane Diallo",
            session_id="session_test_999",
            phone_number="+221776543210",
            answers={"q1": "Oui, validé", "q2": "Immédiat"},
            match_score=95.0,
            status=ApplicationStatus.PRESCREENED
        )

        assert updated.id == "existing-id-123"
        assert updated.full_name == "Ousmane Diallo"
        assert updated.match_score == 95.0
        assert updated.status == ApplicationStatus.PRESCREENED
        assert mock_session.flush.called


class TestRecruiterAgentIntegration:
    """Test suite for RecruiterAgent completion with persistence and notification."""

    @pytest.mark.asyncio
    async def test_interview_completion_triggers_db_and_email(self):
        """Completing Question 5 should trigger PostgreSQL save and background email dispatch."""
        session_id = "test_complete_trigger_session"

        # Initialize interview state at step 4 (about to answer Q5)
        state = {
            "session_id": session_id,
            "stage": "IN_INTERVIEW",
            "current_step": 4,
            "candidate_name": "Babacar Fall",
            "candidate_phone": "+221771112233",
            "answers": {
                "q1_offer_knowledge": "Oui, parfaitement d'accord",
                "q2_availability": "Immédiate",
                "q3_conditions_agreement": "Oui, je valide",
                "q4_technical_skills": "Python, Linux, Docker"
            },
            "cv_parsed": {
                "filename": "cv_babacar.pdf",
                "match_score": 88.0,
                "matched_domains": ["DevOps", "Python"],
                "raw_text": "Babacar Fall CV DevOps"
            }
        }
        await recruiter_agent.save_state(session_id, state)

        # Mock DB save and email dispatch
        with patch.object(CandidateApplicationRepository, "save_application", new_callable=AsyncMock) as mock_db_save:
            with patch.object(CandidateApplicationRepository, "close", new_callable=AsyncMock):
                with patch.object(email_service, "send_recruitment_notification", new_callable=AsyncMock) as mock_email_send:
                    # Candidate answers Q5
                    res = await recruiter_agent.process_candidate_message(
                        session_id=session_id,
                        user_message="Oui, j'ai 2 ans d'expérience sur le terrain.",
                        channel="whatsapp"
                    )

                    assert res is not None
                    assert res["recruiter_stage"] == "COMPLETED"
                    assert res["step"] == 5

                    # Verify DB save was invoked with all details
                    assert mock_db_save.called
                    call_kwargs = mock_db_save.call_args.kwargs
                    assert call_kwargs["full_name"] == "Babacar Fall"
                    assert call_kwargs["phone_number"] == "+221771112233"
                    # Unified score (60% of 88 + 40% of 93 = 90.0)
                    assert call_kwargs["match_score"] >= 88.0
                    assert call_kwargs["cv_filename"] == "cv_babacar.pdf"

                    # Verify response message contains clean confirmation
                    assert "Babacar Fall" in res["message"]
                    assert "CV analysé" in res["message"]
                    assert "%" in res["message"]

    @pytest.mark.asyncio
    async def test_interview_completion_without_cv_scores_questionnaire(self):
        """Candidate completing 5 questions without CV gets scored and domains from questionnaire."""
        session_id = "test_no_cv_trigger_session"

        state = {
            "session_id": session_id,
            "stage": "IN_INTERVIEW",
            "current_step": 4,
            "candidate_name": "Fatou Sow",
            "candidate_phone": "+221772223344",
            "answers": {
                "q1_offer_knowledge": "Oui j'ai bien pris connaissance",
                "q2_availability": "Disponible immédiatement",
                "q3_conditions_agreement": "Oui je valide totalement le cadre",
                "q4_technical_skills": "Énergie solaire photovoltaïque, onduleur, vidéosurveillance caméras"
            },
            "cv_parsed": None
        }
        await recruiter_agent.save_state(session_id, state)

        with patch.object(CandidateApplicationRepository, "save_application", new_callable=AsyncMock) as mock_db_save:
            with patch.object(CandidateApplicationRepository, "close", new_callable=AsyncMock):
                with patch.object(email_service, "send_recruitment_notification", new_callable=AsyncMock):
                    res = await recruiter_agent.process_candidate_message(
                        session_id=session_id,
                        user_message="Oui, j'ai déjà travaillé sur des chantiers d'installation.",
                        channel="whatsapp"
                    )

                    assert res is not None
                    assert res["recruiter_stage"] == "COMPLETED"

                    assert mock_db_save.called
                    call_kwargs = mock_db_save.call_args.kwargs
                    assert call_kwargs["full_name"] == "Fatou Sow"
                    assert call_kwargs["phone_number"] == "+221772223344"
                    # Without CV, score is 100% from questionnaire answers (should be > 80)
                    assert call_kwargs["match_score"] >= 80.0
                    # Target domains should be extracted from Q4 answers!
                    assert "energie_solaire" in call_kwargs["target_domains"]
                    assert "securite_videosurveillance" in call_kwargs["target_domains"]

                    # Response should display questionnaire evaluation score
                    assert "Score d'évaluation" in res["message"]
                    assert "Fatou Sow" in res["message"]

