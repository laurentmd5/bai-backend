"""
Recruiter AI Agent for automated candidate screening.
Manages candidate screening interview flow (5 screening questions) and stores candidate profiles.
"""

import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import json
import re

from app.core.config import settings
from app.core.logging import get_logger
from app.repositories.candidate_repository import CandidateApplicationRepository
from app.services.cache.redis_cache import cache_service, CacheNamespace
from app.services.notification.email_service import email_service
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
        "question": "2️⃣ Quelle est votre disponibilité pour commencer le stage au sein de notre entreprise ?"
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
        company_name = settings.COMPANY_NAME or "notre entreprise"
        
        intro_msg = (
            f"Bonjour{name_mention} ! Chez **{company_name}**, nous sommes constamment à l'écoute des talents"
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
        company_name = settings.COMPANY_NAME or "notre entreprise"
        
        welcome_msg = (
            f"📄 Merci{name_mention} ! Nous avons bien reçu et analysé votre CV (`{filename or 'CV'}`). "
            f"Votre profil a été pré-qualifié avec un score d'adéquation de **{match_score}%**.\n\n"
            f"Afin de finaliser l'évaluation de votre candidature pour l'équipe de **{company_name}**, "
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


    def is_abort_intent(self, message: str) -> bool:
        """Check if candidate wants to abort/stop the interview."""
        if not message:
            return False
        pattern = (
            r"\b("
            r"annuler|annule|stop|arreter|arrêter|arrête|quitter|laisser tomber|laisse tomber|"
            r"(pas|plus|non|guere|guère)\s+(intéressé|interesse|intéréssé|interressé|intéressée|interessee|chaud)|"
            r"m'intéresse\s+(pas|plus)|m'interesse\s+(pas|plus)|"
            r"ne\s+m'intéresse|ne\s+m'interesse|"
            r"ne\s+veux\s+(pas|plus)|veux\s+plus|veux\s+pas|"
            r"pas\s+pour\s+moi|pas\s+intéressant|pas\s+interessant|"
            r"je\s+refuse|refuse|décline|decline|"
            r"autre\s+question|autre\s+chose|changer\s+de\s+sujet|"
            r"non\s+merci|merci\s+au\s+revoir"
            r")\b"
        )
        return bool(re.search(pattern, message, re.IGNORECASE))


    def is_job_vs_stage_objection(self, message: str) -> bool:
        """Check if candidate objects to an internship and insists on a direct job/CDI/CDD."""
        if not message:
            return False
        pattern = (
            r"\b("
            r"pas\s+(de\s+|un\s+|le\s+)?stage|"
            r"veux\s+(un\s+|du\s+)?(emploi|travail|poste|boulot|cdi|cdd)|"
            r"cherche\s+(un\s+|du\s+)?(emploi|travail|poste|boulot|cdi|cdd)|"
            r"emploi\s+direct|travail\s+direct|recrutement\s+direct|embauche\s+directe?|"
            r"uniquement\s+(un\s+)?(emploi|travail|cdi|cdd)|"
            r"pas\s+int[eé]ress[eé]\s+par\s+(un\s+|le\s+)?stage|"
            r"pas\s+de\s+b[eé]n[eé]volat|pas\s+l[aà]\s+pour\s+(un\s+)?stage"
            r")\b"
        )
        return bool(re.search(pattern, message, re.IGNORECASE))

    def is_clarification_or_question(self, message: str, current_step: int = 0) -> Tuple[bool, Optional[str]]:
        """
        Check if user message expresses confusion, doubt, or asks a question about the process.
        Returns (True, explanation_prefix) or (False, None).
        """
        if not message:
            return False, None

        msg_lower = message.lower().strip()

        # Questions or confusion keywords
        confusion_patterns = [
            r"\b(pas vu|aucune annonce|pas d'?annonce|pas vu d'?annonce|tu parles de quoi|parles de quoi|de quoi tu parles|de quoi s'agit-il|c'est quoi ce stage|quel stage|quelle offre|pourquoi ce stage|quel poste|c'est où|c'est quoi|explication|expliquer)\b",
            r"\b(comprends rien|comprends pas|comprends plus|rien compris|pas compris)\b",
            r"\b(problème|probleme|bizarre|ia a un problème|ia a un probleme|bug|erreur)\b",
        ]

        is_confusion = any(re.search(p, msg_lower, re.IGNORECASE) for p in confusion_patterns)
        is_direct_question = "?" in message or any(msg_lower.startswith(w) for w in ["pourquoi", "comment", "où", "quel", "quelle", "c'est quoi", "qui"])

        if is_confusion or is_direct_question:
            company_name = settings.COMPANY_NAME or "notre entreprise"
            app_name = settings.APP_NAME or "votre assistant"
            if current_step == 0 or "annonce" in msg_lower or "stage" in msg_lower or "quoi" in msg_lower:
                explanation = (
                    f"Pas de souci, je vous explique ! Chez **{company_name}**, nous accueillons régulièrement "
                    "des talents techniques (Développement Web/App, Réseaux, Systèmes, Énergie Solaire) pour une période "
                    "d'immersion et d'évaluation, avec de réelles perspectives d'embauche en contrat (CDD/CDI) selon les performances.\n\n"
                    "Afin de transmettre au mieux votre candidature à notre Direction Technique, merci de nous préciser :\n\n"
                )
            elif "problème" in msg_lower or "comprends" in msg_lower:
                explanation = (
                    f"Je vous rassure, tout fonctionne bien ! Je suis {app_name} et je vous pose simplement 5 questions courtes "
                    "pour pré-qualifier votre profil auprès de notre équipe technique.\n\n"
                    "Pour continuer votre évaluation :\n\n"
                )
            else:
                explanation = (
                    "Je comprends votre question ! Ce rapide échange en 5 questions permet à notre Direction Technique "
                    "d'évaluer votre profil et vos disponibilités.\n\n"
                    "Pour poursuivre :\n\n"
                )
            return True, explanation

        return False, None

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

        # 1. Check for abort intent
        if self.is_abort_intent(user_message):
            state["stage"] = "ABORTED"
            state["aborted_at"] = datetime.utcnow().isoformat()
            await self.save_state(session_id, state)
            logger.info("recruitment_interview_aborted", session_id=session_id)
            company_name = settings.COMPANY_NAME or "notre entreprise"
            return {
                "message": (
                    "C'est bien noté, j'interromps le questionnaire de candidature. "
                    f"Comment puis-je vous renseigner sur nos services et expertises chez **{company_name}** ?"
                ),
                "session_id": session_id,
                "recruiter_stage": "ABORTED",
                "step": step,
                "total_steps": 5,
            }

        # 2. Check for "Job vs Stage" objection
        if self.is_job_vs_stage_objection(user_message):
            candidate_name_val = state.get("candidate_name")
            name_prefix = f" {candidate_name_val}" if candidate_name_val and candidate_name_val.lower() != "candidat" else ""
            company_name = settings.COMPANY_NAME or "notre entreprise"
            contact_email = settings.COMPANY_CONTACT_EMAIL or settings.RECRUITER_NOTIFICATION_EMAIL
            email_info = f" par email à **{contact_email}**" if contact_email else ""
            objection_msg = (
                f"C'est tout à fait compréhensible{name_prefix} ! Chez **{company_name}**, pour tous nos profils "
                f"techniques (Développement Web/App, Réseaux, Systèmes, Énergie Solaire), ce stage d'immersion et d'évaluation "
                f"constitue justement notre sas de recrutement direct permettant de valider les compétences pratiques sur des projets clients "
                f"avant la délivrance d'un contrat d'embauche (**CDD ou CDI**).\n\n"
                f"📄 **Pour les profils expérimentés / seniors** :\n"
                f"Si vous possédez déjà une solide expérience et préférez postuler directement sans passer par cette étape de pré-qualification, "
                f"vous pouvez envoyer directement votre CV détaillé à la Direction{email_info} "
                f"ou nous le transmettre ici-même au format PDF/Word.\n\n"
                f"Souhaitez-vous poursuivre l'évaluation pour cette opportunité, ou préférez-vous nous transmettre directement votre CV ?"
            )
            logger.info("recruitment_job_vs_stage_objection_handled", session_id=session_id, step=step)
            return {
                "message": objection_msg,
                "session_id": session_id,
                "recruiter_stage": "IN_INTERVIEW",
                "step": step + 1,
                "total_steps": 5,
                "fallback_triggered": False,
            }

        # 3. Check for negative answer to Q1 (Offer knowledge)
        is_q1_negation = (step == 0) and bool(
            re.search(r"^(non|pas encore|pas du tout|jamais|pas vu|aucune idée|aucune)\b", user_message.strip(), re.IGNORECASE)
        )
        if is_q1_negation:
            candidate_name_val = state.get("candidate_name")
            name_prefix = f" {candidate_name_val}" if candidate_name_val and candidate_name_val.lower() != "candidat" else ""
            company_name = settings.COMPANY_NAME or "notre entreprise"
            q1_explanation = (
                f"Aucun souci{name_prefix} ! Je vous résume le cadre : chez **{company_name}**, nous accueillons régulièrement "
                f"des profils techniques pour une phase d'immersion et d'évaluation pratique. Cette période permet de tester vos compétences "
                f"sur le terrain et débouche directement sur un contrat d'embauche (**CDD ou CDI**) selon vos performances.\n\n"
                f"Afin de transmettre au mieux votre dossier à notre Direction Technique, pourriez-vous me préciser : \n\n"
                f"{SCREENING_QUESTIONS[1]['question']}"
            )
            q_id = SCREENING_QUESTIONS[0]["id"]
            state["answers"][q_id] = "Non (briefé par l'assistant)"
            state["current_step"] = 1
            await self.save_state(session_id, state)
            logger.info("recruitment_q1_negation_handled", session_id=session_id)
            return {
                "message": q1_explanation,
                "session_id": session_id,
                "recruiter_stage": "IN_INTERVIEW",
                "step": 2,
                "total_steps": 5,
                "fallback_triggered": False,
            }

        # 4. Check for question, doubt or confusion (Clarification without advancing step)
        is_clarification, explanation_prefix = self.is_clarification_or_question(user_message, current_step=step)
        if is_clarification and step < len(SCREENING_QUESTIONS):
            current_q = SCREENING_QUESTIONS[step]["question"]
            clarification_msg = f"{explanation_prefix}{current_q}"
            logger.info("recruitment_clarification_provided", session_id=session_id, step=step)

            return {
                "message": clarification_msg,
                "session_id": session_id,
                "recruiter_stage": "IN_INTERVIEW",
                "step": step + 1,
                "total_steps": 5,
                "fallback_triggered": False,
            }

        # 5. Valid answer: record and advance to next question

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

            phone_val = state.get("phone_number") or state.get("candidate_phone")
            email_val = state.get("candidate_email")
            answers_dict = state.get("answers", {})
            cv_info = state.get("cv_parsed") or {}
            cv_filename = cv_info.get("filename")
            raw_cv_text = cv_info.get("raw_text")
            match_score = float(cv_info.get("match_score", 0.0))
            target_domains = cv_info.get("matched_domains") or []

            # 1. Persist application to PostgreSQL asynchronously
            try:
                candidate_repo = CandidateApplicationRepository()
                await candidate_repo.save_application(
                    full_name=candidate_name_val or "Candidat",
                    phone_number=phone_val,
                    email=email_val,
                    session_id=session_id,
                    channel=channel,
                    answers=answers_dict,
                    parsed_cv=cv_info if cv_info else None,
                    cv_filename=cv_filename,
                    raw_cv_text=raw_cv_text,
                    match_score=match_score,
                    target_domains=target_domains,
                )
                await candidate_repo.close()
                logger.info("recruitment_db_persistence_success", session_id=session_id)
            except Exception as db_err:
                logger.error("recruitment_db_persistence_failed", session_id=session_id, error=str(db_err))

            # 2. Trigger non-blocking email notification in background
            try:
                asyncio.create_task(
                    email_service.send_recruitment_notification(
                        full_name=candidate_name_val or "Candidat",
                        phone_number=phone_val,
                        email=email_val,
                        channel=channel,
                        answers=answers_dict,
                        cv_info=cv_info if cv_info else None,
                        match_score=match_score,
                        target_domains=target_domains,
                    )
                )
            except Exception as email_err:
                logger.error("recruitment_email_trigger_failed", session_id=session_id, error=str(email_err))

            has_cv = bool(cv_info)
            company_label = settings.COMPANY_NAME or "notre entreprise"
            contact_email = settings.COMPANY_CONTACT_EMAIL or settings.RECRUITER_NOTIFICATION_EMAIL
            contact_phone = settings.COMPANY_CONTACT_PHONE

            email_send_msg = f" ou par email à **{contact_email}**" if contact_email else ""
            reach_email_msg = f" par email à **{contact_email}**" if contact_email else ""
            reach_phone_msg = f" ou au **{contact_phone}**" if contact_phone else ""

            reach_info = ""
            if reach_email_msg or reach_phone_msg:
                reach_info = f"\n\nVous pouvez également nous joindre directement{reach_email_msg}{reach_phone_msg}."

            if has_cv:
                score_mention = f" (Score de matching : **{match_score:.0f}%**)" if match_score else ""
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
                    f"N'hésitez pas à nous envoyer votre **CV (au format PDF ou Word)** directement ici sur WhatsApp{email_send_msg}.\n\n"
                )

            final_response = (
                f"✅ **Merci infiniment pour vos réponses{name_suffix} !**\n\n"
                f"{dossier_text} et transmises à l'équipe de recrutement chez **{company_label}**.\n\n"
                f"{cv_instruction}"
                f"📌 **Prochaines étapes** :\n"
                f"- Examen approfondi de votre profil sous 48h à 72h.\n"
                f"- Si votre profil est retenu, nous vous contacterons directement par téléphone ou WhatsApp pour convenir d'un entretien technique.\n"
                f"{reach_info}"
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

