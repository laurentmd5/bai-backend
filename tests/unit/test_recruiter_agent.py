"""
Unit tests for Recruiter Agent.
Tests screening questionnaire progression, state persistence, text intent detection, personalization, and completion.
"""

import pytest
from app.services.recruitment.recruiter_agent import recruiter_agent, SCREENING_QUESTIONS
from app.services.validation.output_validator import OutputValidator


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
    async def test_recruitment_intent_detection(self):
        """Verify keyword intent detection for jobs/internships."""
        is_rec, role = recruiter_agent.is_recruitment_intent("Je suis à la recherche d’un emploi, je suis développeur.")
        assert is_rec is True
        assert role == "Développeur"

        is_rec2, role2 = recruiter_agent.is_recruitment_intent("Je suis entièrement disponible pour un stage.")
        assert is_rec2 is True

        is_rec3, role3 = recruiter_agent.is_recruitment_intent("Quel est le prix d'une caméra IP ?")
        assert is_rec3 is False

    @pytest.mark.asyncio
    async def test_text_initiated_interview_flow_with_name_and_no_cv(self):
        """
        Candidate applies via text with WhatsApp profile name.
        Verifies:
        - Greeting contains candidate name
        - Sequential progression
        - Final response does NOT mention 'CV analysé' if no CV was uploaded
        - Final response warmly invites candidate to send CV.
        """
        session_id = "test_text_candidate_session_456"

        # 1. Text application start with caller name
        res = await recruiter_agent.start_text_interview(
            session_id=session_id,
            role="Développeur",
            user_message="Je suis développeur à la recherche d'un stage.",
            candidate_name="Laurent MAVOUNGOU"
        )
        assert res["recruiter_stage"] == "IN_INTERVIEW"
        assert res["step"] == 1
        assert "Laurent MAVOUNGOU" in res["message"]
        assert "1️⃣" in res["message"]

        # 2. Answer Q1
        q1_res = await recruiter_agent.process_candidate_message(
            session_id=session_id,
            user_message="Oui oui"
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
            user_message="Oui je sais et je suis informé que ce stage n'est pas rémunéré au départ."
        )
        assert q3_res["step"] == 4
        assert "4️⃣" in q3_res["message"]
        assert "compétences" in q3_res["message"].lower()

        # 5. Answer Q4
        q4_res = await recruiter_agent.process_candidate_message(
            session_id=session_id,
            user_message="FastAPI, Next.js, React, PostgreSQL."
        )
        assert q4_res["step"] == 5
        assert "5️⃣" in q4_res["message"]
        assert "terrain" in q4_res["message"].lower()

        # 6. Answer Q5
        final_res = await recruiter_agent.process_candidate_message(
            session_id=session_id,
            user_message="Oui, j'ai déployé des serveurs et réseaux sur site."
        )
        assert final_res["recruiter_stage"] == "COMPLETED"
        assert "Laurent MAVOUNGOU" in final_res["message"]
        # Must NOT claim CV was analyzed if no CV was sent!
        assert "CV analysé" not in final_res["message"]
        # Must invite candidate to send CV
        assert "Pour compléter et valoriser au mieux votre dossier" in final_res["message"]
        assert "adiarraa@gmail.com" in final_res["message"]

    @pytest.mark.asyncio
    async def test_full_cv_interview_flow(self):
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
        assert "Aminata SOW" in res["message"]
        assert "1️⃣" in res["message"]

        # 2. Answer Q1 to Q5
        for i in range(4):
            await recruiter_agent.process_candidate_message(
                session_id=session_id,
                user_message=f"Réponse test {i+1}"
            )
        
        final_res = await recruiter_agent.process_candidate_message(
            session_id=session_id,
            user_message="Réponse finale Q5"
        )
        assert final_res["recruiter_stage"] == "COMPLETED"
        assert "Aminata SOW" in final_res["message"]
        assert "CV analysé" in final_res["message"]


class TestOutputSanitizer:
    """Test output validator sanitization of leaked prompt markers."""

    def test_cleans_leaked_prompt_template_markers(self):
        """Verify *QUESTION :* and *RÉPONSE :* prompt artifacts are cleanly stripped."""
        validator = OutputValidator()
        dirty_response = (
            "Parfait ! Je prends note de votre accord.\n\n"
            "*QUESTION :* Je suis informé que ce stage n'est pas rémunéré.\n"
            "*RÉPONSE :*"
        )
        is_valid, cleaned, meta = validator.validate_response(
            response=dirty_response,
            sources=[],
            channel="whatsapp",
            strict_mode=False
        )
        assert "*QUESTION :*" not in cleaned
        assert "*RÉPONSE :*" not in cleaned
        assert "Parfait ! Je prends note de votre accord." in cleaned
