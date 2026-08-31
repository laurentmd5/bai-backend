"""
Unit tests for Recruiter Agent.
Tests screening questionnaire progression, state persistence, and completion.
"""

import pytest
from app.services.recruitment.recruiter_agent import recruiter_agent, SCREENING_QUESTIONS


class TestRecruiterAgent:
    """Tests for interactive recruiter screening interview."""

    @pytest.mark.asyncio
    async def test_screening_questions_count(self):
        """Verify the 5 official NETSYSTEME screening questions exist."""
        assert len(SCREENING_QUESTIONS) == 5
        assert "stage" in SCREENING_QUESTIONS[0]["question"].lower()
        assert "disponibilité" in SCREENING_QUESTIONS[1]["question"].lower()
        assert "rémunéré" in SCREENING_QUESTIONS[2]["question"].lower()
        assert "compétences" in SCREENING_QUESTIONS[3]["question"].lower()
        assert "terrain" in SCREENING_QUESTIONS[4]["question"].lower()

    @pytest.mark.asyncio
    async def test_full_interview_flow(self):
        """Simulate a candidate submitting a CV and answering all 5 questions sequentially."""
        session_id = "test_candidate_session_123"
        cv_text = "Aminata SOW - Ingénieur Réseaux et Télécoms. Compétences Cisco, VoIP Asterisk, Câblage VDI."
        
        # 1. CV submission
        res = await recruiter_agent.handle_cv_submission(
            session_id=session_id,
            raw_text=cv_text,
            filename="cv_aminata.pdf",
            phone_number="+221770000000",
            channel="whatsapp"
        )
        assert res["recruiter_stage"] == "IN_INTERVIEW"
        assert res["step"] == 1
        assert "1️⃣" in res["message"]

        # 2. Answer Q1
        q1_res = await recruiter_agent.process_candidate_message(
            session_id=session_id,
            user_message="Oui, j'ai bien pris connaissance et je souhaite m'investir pour obtenir un contrat."
        )
        assert q1_res["step"] == 2
        assert "2️⃣" in q1_res["message"]

        # 3. Answer Q2
        q2_res = await recruiter_agent.process_candidate_message(
            session_id=session_id,
            user_message="Je suis disponible immédiatement."
        )
        assert q2_res["step"] == 3
        assert "3️⃣" in q2_res["message"]

        # 4. Answer Q3
        q3_res = await recruiter_agent.process_candidate_message(
            session_id=session_id,
            user_message="Je suis parfaitement informé et d'accord avec les conditions."
        )
        assert q3_res["step"] == 4
        assert "4️⃣" in q3_res["message"]

        # 5. Answer Q4
        q4_res = await recruiter_agent.process_candidate_message(
            session_id=session_id,
            user_message="Réseaux IP, VoIP Grandstream, caméras de sécurité."
        )
        assert q4_res["step"] == 5
        assert "5️⃣" in q4_res["message"]

        # 6. Answer Q5 (Final)
        final_res = await recruiter_agent.process_candidate_message(
            session_id=session_id,
            user_message="J'ai réalisé du câblage réseau et l'installation de caméras IP sur des sites clients."
        )
        assert final_res["recruiter_stage"] == "COMPLETED"
        assert "Ameth DIARRA" in final_res["message"]
        assert "adiarraa@gmail.com" in final_res["message"]
