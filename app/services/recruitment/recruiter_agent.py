"""
Recruiter AI Agent for NETSYSTEME INFORMATIQUE.
Manages candidate screening interview flow (5 NETSYSTEME questions) and stores candidate profiles.
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import json

from app.core.logging import get_logger
from app.services.cache.redis_cache import cache_service, CacheNamespace
from app.services.recruitment.cv_parser_service import cv_parser_service

logger = get_logger(__name__)

SCREENING_QUESTIONS = [
    {
        "id": "q1_offer_knowledge",
        "question": (
            "1️⃣ Avez-vous bien pris connaissance de notre offre de stage ? "
            "Comme indiqué dans l’annonce, il s’agit d’un stage d'immersion et d'évaluation "
            "pouvant déboucher sur un contrat (CDD/CDI) en fonction de vos performances."
        )
    },
    {
        "id": "q2_availability",
        "question": "2️⃣ Quelle est votre disponibilité pour commencer le stage chez NETSYSTEME ?"
    },
    {
        "id": "q3_conditions_agreement",
        "question": (
            "3️⃣ Êtes-vous informé(e) que ce stage d'évaluation n’est pas rémunéré au départ ? "
            "En revanche, dès que vos performances sont satisfaisantes et que vous faites preuve d’efficacité, "
            "nous réévaluons immédiatement votre situation pour une prise en charge de vos frais de transport, "
            "ainsi qu’une évolution vers un contrat d'embauche. Êtes-vous en phase avec ce cadre ?"
        )
    },
    {
        "id": "q4_technical_skills",
        "question": (
            "4️⃣ Quelles sont vos principales compétences techniques et professionnelles "
            "(ex: Réseaux, Solaire, Vidéosurveillance, Câblage VDI, Développement Web, VoIP, etc.) ?"
        )
    },
    {
        "id": "q5_field_experience",
        "question": (
            "5️⃣ Avez-vous déjà effectué des travaux de terrain ou des interventions sur site ? "
            "Si oui, merci de préciser dans quel domaine et de décrire brièvement votre expérience."
        )
    }
]


class RecruiterAgent:
    """Conversational AI agent acting as NETSYSTEME Technical Recruiter."""

    def __init__(self):
        self._memory_store: Dict[str, Dict[str, Any]] = {}

    async def get_state(self, session_id: str) -> Dict[str, Any]:
        """Retrieve current candidate session state."""
        try:
            state = await cache_service.get(CacheNamespace.SESSIONS, f"recruitment_state:{session_id}")
            if state and isinstance(state, dict):
                return state
        except Exception:
            pass

        if session_id in self._memory_store:
            return self._memory_store[session_id]

        return {
            "session_id": session_id,
            "stage": "IDLE",  # IDLE, IN_INTERVIEW, COMPLETED
            "current_step": 0,
            "cv_parsed": None,
            "answers": {},
            "started_at": datetime.utcnow().isoformat()
        }

    async def save_state(self, session_id: str, state: Dict[str, Any]) -> None:
        """Persist candidate session state in Redis and memory."""
        self._memory_store[session_id] = state
        try:
            await cache_service.set(
                CacheNamespace.SESSIONS,
                f"recruitment_state:{session_id}",
                state,
                ttl=86400  # 24h
            )
        except Exception:
            pass

    def is_recruitment_intent(self, message: str) -> Tuple[bool, str]:
        """
        Check if user message expresses a job, stage, or employment application intent.
        Returns (is_intent, detected_role).
        """
        msg = (message or "").lower()
        
        triggers = [
            "emploi", "stage", "postuler", "candidature", "embauche", "recrutement",
            "développeur", "developpeur", "technicien", "stagiaire", "ingénieur", "ingenieur",
            "cherche un travail", "cherche du travail", "recherche un emploi", "recherche un stage",
            "cherche un stage", "cherche un emploi", "disponible pour un stage", "offre de stage"
        ]
        
        has_intent = any(t in msg for t in triggers)
        
        role = ""
        if "développeur" in msg or "developpeur" in msg or "dev" in msg:
            role = "Développeur"
        elif "technicien" in msg or "reseau" in msg or "réseau" in msg:
            role = "Technicien Réseaux / Télécom"
        elif "solaire" in msg or "photovolta" in msg:
            role = "Technicien Énergie Solaire"
        elif "stage" in msg:
            role = "Stagiaire"
            
        return has_intent, role

    async def start_text_interview(
        self,
        session_id: str,
        role: str = "",
        user_message: str = "",
        channel: str = "whatsapp",
        candidate_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Start the 5-step screening interview when candidate expresses intent via text.
        """
        state = await self.get_state(session_id)
        state["stage"] = "IN_INTERVIEW"
        state["current_step"] = 0
        state["role_target"] = role or "Candidat"
        if candidate_name and candidate_name.strip() and candidate_name.lower() != "candidat":
            state["candidate_name"] = candidate_name.strip()
        state["answers"] = {}
        
        await self.save_state(session_id, state)
        
        first_q = SCREENING_QUESTIONS[0]["question"]
        name_mention = f" {state['candidate_name']}" if state.get("candidate_name") else ""
        role_mention = f" pour un profil **{role}**" if role else ""
        
        intro_msg = (
            f"Bonjour{name_mention} ! Chez **NETSYSTEME INFORMATIQUE**, nous sommes constamment à l'écoute des talents"
            f"{role_mention}.\n\n"
            f"Afin d'évaluer votre profil et de transmettre votre candidature à notre Direction Technique, "
            f"merci de répondre à nos **5 questions de présélection** (vous pouvez également nous envoyer votre CV au format PDF/Word à tout moment) :\n\n"
            f"{first_q}"
        )
        
        return {
            "message": intro_msg,
            "session_id": session_id,
            "recruiter_stage": "IN_INTERVIEW",
            "step": 1,
            "total_steps": 5,
        }

    async def handle_cv_submission(
        self,
        session_id: str,
        raw_text: str,
        filename: Optional[str] = None,
        phone_number: Optional[str] = None,
        channel: str = "whatsapp"
    ) -> Dict[str, Any]:
        """
        Triggered when a candidate sends a CV file (PDF/DOCX).
        Parses the CV and starts or updates the 5-step screening interview.
        """
        parsed_cv = await cv_parser_service.parse_cv_text(raw_text, filename=filename)
        
        state = await self.get_state(session_id)
        state["stage"] = "IN_INTERVIEW"
        state["current_step"] = 0
        state["cv_parsed"] = parsed_cv
        state["phone_number"] = phone_number or parsed_cv.get("phone")
        if parsed_cv.get("full_name"):
            state["candidate_name"] = parsed_cv.get("full_name")
        elif not state.get("candidate_name"):
            state["candidate_name"] = "Candidat"
        
        await self.save_state(session_id, state)
        
        first_q = SCREENING_QUESTIONS[0]["question"]
        candidate_name = state.get("candidate_name", "Candidat")
        name_mention = f" {candidate_name}" if candidate_name and candidate_name.lower() != "candidat" else ""
        match_score = parsed_cv.get("match_score", 0)
        
        welcome_msg = (
            f"📄 Merci{name_mention} ! Nous avons bien reçu et analysé votre CV (`{filename or 'CV'}`). "
            f"Votre profil a été pré-qualifié avec un score d'adéquation de **{match_score}%**.\n\n"
            f"Afin de finaliser l'évaluation de votre candidature pour l'équipe de **NETSYSTEME INFORMATIQUE**, "
            f"merci de répondre à nos **5 questions de présélection** :\n\n"
            f"{first_q}"
        )
        
        return {
            "message": welcome_msg,
            "session_id": session_id,
            "recruiter_stage": "IN_INTERVIEW",
            "step": 1,
            "total_steps": 5,
            "cv_parsed": parsed_cv
        }


    async def process_candidate_message(
        self,
        session_id: str,
        user_message: str,
        channel: str = "web",
        candidate_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Process user response during the screening interview.
        Returns None if session is not currently in an interview.
        """
        state = await self.get_state(session_id)
        if state.get("stage") != "IN_INTERVIEW":
            return None

        if candidate_name and candidate_name.strip() and candidate_name.lower() != "candidat":
            if not state.get("candidate_name") or state.get("candidate_name") == "Candidat":
                state["candidate_name"] = candidate_name.strip()

        step = state.get("current_step", 0)
        if step < len(SCREENING_QUESTIONS):
            q_id = SCREENING_QUESTIONS[step]["id"]
            state["answers"][q_id] = user_message.strip()
            step += 1
            state["current_step"] = step

        if step < len(SCREENING_QUESTIONS):
            # Ask next question
            next_q = SCREENING_QUESTIONS[step]["question"]
            await self.save_state(session_id, state)
            
            return {
                "message": next_q,
                "session_id": session_id,
                "recruiter_stage": "IN_INTERVIEW",
                "step": step + 1,
                "total_steps": 5,
                "fallback_triggered": False
            }
        else:
            # Interview complete
            state["stage"] = "COMPLETED"
            state["completed_at"] = datetime.utcnow().isoformat()
            await self.save_state(session_id, state)
            
            candidate_name_val = state.get("candidate_name")
            name_suffix = f", {candidate_name_val}" if candidate_name_val and candidate_name_val.lower() != "candidat" else ""
            
            has_cv = bool(state.get("cv_parsed"))
            if has_cv:
                cv_info = state.get("cv_parsed") or {}
                match_score = cv_info.get("match_score", 0)
                score_mention = f" (Score de matching : **{match_score}%**)" if match_score else ""
                dossier_text = (
                    f"Votre dossier complet de candidature (**CV analysé{score_mention} + Réponses aux 5 questions de présélection**)"
                )
                cv_instruction = ""
            else:
                dossier_text = (
                    "Vos réponses aux **5 questions de présélection** ont été enregistrées avec succès"
                )
                cv_instruction = (
                    "📄 **Pour compléter et valoriser au mieux votre dossier** :\n"
                    "N'hésitez pas à nous envoyer votre **CV (au format PDF ou Word)** directement ici sur WhatsApp ou par email à **adiarraa@gmail.com**.\n\n"
                )

            final_response = (
                f"✅ **Merci infiniment pour vos réponses{name_suffix} !**\n\n"
                f"{dossier_text} et transmises à la Direction Générale (M. Ameth DIARRA) "
                f"et à notre équipe technique chez **NETSYSTEME INFORMATIQUE**.\n\n"
                f"{cv_instruction}"
                f"📌 **Prochaines étapes** :\n"
                f"- Examen approfondi de votre profil sous 48h à 72h.\n"
                f"- Si votre profil est retenu, nous vous contacterons directement par téléphone ou WhatsApp pour un entretien technique au siège (Cité Keur Gorgui, Immeuble Horizon).\n\n"
                f"Vous pouvez également nous joindre directement par email à **adiarraa@gmail.com** ou au **+221 33 827 28 45**."
            )
            
            logger.info("recruitment_interview_completed", session_id=session_id, candidate=candidate_name_val, has_cv=has_cv)
            
            return {
                "message": final_response,
                "session_id": session_id,
                "recruiter_stage": "COMPLETED",
                "step": 5,
                "total_steps": 5,
                "candidate_profile": state
            }


recruiter_agent = RecruiterAgent()

