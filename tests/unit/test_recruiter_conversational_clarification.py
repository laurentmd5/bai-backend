"""
Unit tests for RecruiterAgent conversational clarifications and abort handling.
Verifies that doubts, questions, and confusion do not blindly advance the questionnaire.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.recruitment.recruiter_agent import RecruiterAgent, SCREENING_QUESTIONS


@pytest.fixture
def recruiter():
    agent = RecruiterAgent()
    agent.save_state = AsyncMock()
    return agent


@pytest.mark.asyncio
async def test_recruiter_handles_unseen_ad_clarification(recruiter):
    """When candidate says 'Je n'ai vu aucune annonce', explain and stay on Q1."""
    session_id = "test-session-clarif-1"
    initial_state = {
        "stage": "IN_INTERVIEW",
        "current_step": 0,
        "candidate_name": "Laurent",
        "answers": {}
    }
    recruiter.get_state = AsyncMock(return_value=initial_state)

    res = await recruiter.process_candidate_message(
        session_id=session_id,
        user_message="Je n’ai vu aucune annonce",
        candidate_name="Laurent"
    )

    assert res is not None
    assert res["recruiter_stage"] == "IN_INTERVIEW"
    assert res["step"] == 1
    # Must contain explanation and repeat Q1
    assert "NETSYSTEME INFORMATIQUE" in res["message"]
    assert SCREENING_QUESTIONS[0]["question"] in res["message"]
    # Answers must still be empty for Q1
    assert "q1_offer_knowledge" not in initial_state["answers"]


@pytest.mark.asyncio
async def test_recruiter_handles_confusion_question(recruiter):
    """When candidate asks 'Tu parles de quoi ?', explain without advancing."""
    session_id = "test-session-clarif-2"
    initial_state = {
        "stage": "IN_INTERVIEW",
        "current_step": 0,
        "candidate_name": "Laurent",
        "answers": {}
    }
    recruiter.get_state = AsyncMock(return_value=initial_state)

    res = await recruiter.process_candidate_message(
        session_id=session_id,
        user_message="Tu parles de quoi ?",
        candidate_name="Laurent"
    )

    assert res is not None
    assert res["recruiter_stage"] == "IN_INTERVIEW"
    assert "NETSYSTEME" in res["message"]
    assert SCREENING_QUESTIONS[0]["question"] in res["message"]


@pytest.mark.asyncio
async def test_recruiter_handles_abort(recruiter):
    """When candidate says 'Annuler' or 'Stop', exit interview cleanly."""
    session_id = "test-session-abort"
    initial_state = {
        "stage": "IN_INTERVIEW",
        "current_step": 2,
        "candidate_name": "Laurent",
        "answers": {"q1_offer_knowledge": "Oui"}
    }
    recruiter.get_state = AsyncMock(return_value=initial_state)

    res = await recruiter.process_candidate_message(
        session_id=session_id,
        user_message="Je préfère annuler",
        candidate_name="Laurent"
    )

    assert res is not None
    assert res["recruiter_stage"] == "ABORTED"
    assert "interromps le questionnaire" in res["message"]


@pytest.mark.asyncio
async def test_recruiter_proceeds_on_valid_answer(recruiter):
    """When candidate answers normally, advance to next question."""
    session_id = "test-session-normal"
    initial_state = {
        "stage": "IN_INTERVIEW",
        "current_step": 0,
        "candidate_name": "Laurent",
        "answers": {}
    }
    recruiter.get_state = AsyncMock(return_value=initial_state)

    res = await recruiter.process_candidate_message(
        session_id=session_id,
        user_message="Oui j'ai bien pris connaissance de l'offre",
        candidate_name="Laurent"
    )

    assert res is not None
    assert res["recruiter_stage"] == "IN_INTERVIEW"
    assert res["step"] == 2
    assert SCREENING_QUESTIONS[1]["question"] in res["message"]
    assert initial_state["answers"]["q1_offer_knowledge"] == "Oui j'ai bien pris connaissance de l'offre"
