"""
Sales AI Agent for automated commercial qualification and quote request handling.
Manages progressive qualification of prospects and alerts the sales team upon completion.
"""

import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import re

from app.core.config import settings
from app.core.logging import get_logger
from app.repositories.lead_repository import CommercialLeadRepository
from app.services.cache.redis_cache import cache_service, CacheNamespace
from app.services.notification.email_service import email_service

logger = get_logger(__name__)

# Key business categories offered by NETSYSTEME
SERVICE_CATEGORIES = {
    "Vidéosurveillance": ["camera", "caméra", "surveillance", "vms", "dvr", "nvr", "hikvision", "dahua", "cctv"],
    "Énergie Solaire": ["solaire", "panneau", "photovolta", "batterie", "onduleur solaire", "kwh", "centrale"],
    "Réseaux & Télécom": ["réseau", "reseau", "cablage", "câblage", "vdi", "baie", "switch", "routeur", "wifi", "fibre", "ipbx", "voip"],
    "Sites Web & Plateformes": ["site web", "site internet", "e-commerce", "ecommerce", "application web", "plateforme", "react", "next.js", "nextjs"],
    "Sécurité & Domotique": ["domotique", "alarme", "biométrie", "biometrie", "badge", "rfid", "controle d'acces", "contrôle d'accès"],
    "Courant Fort & Faible": ["courant fort", "courant faible", "tgbt", "groupe electrogene", "électrogène", "onduleur"],
    "Sécurité Incendie": ["incendie", "extincteur", "désenfumage", "detection incendie", "détection incendie"],
    "Logiciels & ERP": ["odoo", "erp", "crm", "logiciel sur mesure", "logiciel de gestion"],
    "IPTV & Audiovisuel": ["iptv", "affichage dynamique", "visio", "visioconférence", "sonorisation"],
}


class SalesAgent:
    """Conversational AI agent acting as NETSYSTEME Commercial / Sales Qualifier."""

    def __init__(self):
        self._memory_store: Dict[str, Dict[str, Any]] = {}

    async def get_state(self, session_id: str) -> Dict[str, Any]:
        """Retrieve current prospect sales session state."""
        try:
            state = await cache_service.get(CacheNamespace.SESSIONS, f"sales_lead_state:{session_id}")
            if state and isinstance(state, dict):
                return state
        except Exception:
            pass

        if session_id in self._memory_store:
            return self._memory_store[session_id]

        return {
            "session_id": session_id,
            "stage": "IDLE",  # IDLE, COLLECTING_NEED, COLLECTING_CONTACT, COLLECTING_LOCATION, COMPLETED, ABORTED
            "requirements": [],
            "category": None,
            "full_name": None,
            "company_name": None,
            "phone_number": None,
            "email": None,
            "location": None,
            "answers": {},
            "started_at": datetime.utcnow().isoformat(),
        }

    async def save_state(self, session_id: str, state: Dict[str, Any]) -> None:
        """Persist prospect session state in Redis and in-memory fallback."""
        self._memory_store[session_id] = state
        try:
            await cache_service.set(
                CacheNamespace.SESSIONS,
                f"sales_lead_state:{session_id}",
                state,
                ttl=86400  # 24h
            )
        except Exception:
            pass

    def detect_service_category(self, text: str) -> Optional[str]:
        """Identify which service category the prospect is inquiring about."""
        lower_text = (text or "").lower()
        for category, keywords in SERVICE_CATEGORIES.items():
            if any(kw in lower_text for kw in keywords):
                return category
        return None

    def is_quote_or_sales_intent(self, message: str) -> Tuple[bool, Optional[str]]:
        """
        Determine if the user is asking for a quote, pricing, purchasing, or project installation.
        Returns (has_intent, category).
        """
        msg = (message or "").lower()

        # Direct quote / purchase triggers
        triggers = [
            "devis", "tarif", "combien coûte", "combien coute", "prix", "acheter",
            "commander", "installer", "combien pour", "proposition commerciale",
            "facture proforma", "proforma", "offre de prix", "voulez-vous me faire un devis",
            "je veux acheter", "je souhaite acheter", "je voudrais commander", "je veux une caméra",
            "je veux des caméras", "je veux installer", "besoin d'une installation",
            "je veux un devis", "demande de devis"
        ]

        has_intent = any(t in msg for t in triggers)
        category = self.detect_service_category(msg)

        return has_intent, category

    def extract_contact_info(self, text: str) -> Dict[str, Optional[str]]:
        """
        Extract phone number, email and potentially name from a message string.
        """
        results: Dict[str, Optional[str]] = {
            "phone": None,
            "email": None,
            "name": None,
        }

        # 1. Email extraction regex
        email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
        if email_match:
            results["email"] = email_match.group(0).strip().lower()

        # 2. Phone extraction regex (handles international and Senegalese formats +221, 77, 78, 76, 70, 33)
        phone_match = re.search(r'(\+?221\s?)?([783]\d{1}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}|\d{9,15})', text)
        if phone_match:
            phone_str = phone_match.group(0).strip()
            # Clean spaces and hyphens
            cleaned_phone = re.sub(r'[\s.-]', '', phone_str)
            if len(cleaned_phone) >= 8:
                results["phone"] = phone_str

        # 3. Simple name pattern if introduced with "je m'appelle", "moi c'est", "nom:"
        name_match = re.search(r"(?:je m'appelle|moi c'est|nom\s*:\s*|mon nom est)\s+([A-Za-zÀ-ÿ\s'-]{2,40})", text, re.IGNORECASE)
        if name_match:
            results["name"] = name_match.group(1).strip().title()

        return results

    async def start_sales_qualification(
        self,
        session_id: str,
        user_message: str,
        channel: str = "web",
        client_name: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initialize the sales qualification tunnel when a quote or purchase intent is expressed.
        """
        state = await self.get_state(session_id)
        state["stage"] = "COLLECTING_NEED"
        state["channel"] = channel
        detected_cat = category or self.detect_service_category(user_message) or "Prestation Technique"
        state["category"] = detected_cat

        if user_message:
            state["requirements"].append(user_message.strip())

        extracted = self.extract_contact_info(user_message)
        if extracted["phone"]:
            state["phone_number"] = extracted["phone"]
        if extracted["email"]:
            state["email"] = extracted["email"]
        if extracted["name"]:
            state["full_name"] = extracted["name"]
        elif client_name and client_name.strip() and client_name.lower() not in ("user", "candidat", "client"):
            state["full_name"] = client_name.strip()

        await self.save_state(session_id, state)

        company_label = settings.COMPANY_NAME or "NETSYSTEME"
        name_prefix = f" {state['full_name']}" if state.get("full_name") else ""

        reply = (
            f"Avec plaisir{name_prefix} ! Chez **{company_label}**, nous établissons des devis personnalisés pour vos projets en **{detected_cat}**.\n\n"
            "Pour vous préparer une proposition chiffrée précise :\n"
            "1️⃣ **Quel est votre besoin précis et les quantités envisagées ?** (ex: nombre d'équipements, surface, site particulier ou professionnel) ?"
        )

        return {
            "message": reply,
            "session_id": session_id,
            "sales_stage": "COLLECTING_NEED",
            "category": detected_cat,
        }

    async def process_prospect_message(
        self,
        session_id: str,
        user_message: str,
        channel: str = "web",
        client_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Process user message while in a sales qualification conversation.
        Returns None if session is not currently in a sales qualification flow.
        """
        state = await self.get_state(session_id)
        stage = state.get("stage")

        if stage not in ("COLLECTING_NEED", "COLLECTING_CONTACT", "COLLECTING_LOCATION"):
            return None

        # Check for cancel or abort
        msg_lower = user_message.lower().strip()
        if any(w in msg_lower for w in ("annuler le devis", "annuler", "laisser tomber", "stop devis", "non merci")):
            state["stage"] = "ABORTED"
            await self.save_state(session_id, state)
            company_label = settings.COMPANY_NAME or "NETSYSTEME"
            return {
                "message": f"C'est bien noté. Comment puis-je vous aider par ailleurs sur les services de **{company_label}** ?",
                "session_id": session_id,
                "sales_stage": "ABORTED",
            }

        # Extract contact info in any message
        extracted = self.extract_contact_info(user_message)
        if extracted["phone"] and not state.get("phone_number"):
            state["phone_number"] = extracted["phone"]
        if extracted["email"] and not state.get("email"):
            state["email"] = extracted["email"]
        if extracted["name"] and not state.get("full_name"):
            state["full_name"] = extracted["name"]

        # STAGE 1: Need & Requirements Collection
        if stage == "COLLECTING_NEED":
            state["requirements"].append(user_message.strip())
            cat = self.detect_service_category(user_message)
            if cat:
                state["category"] = cat

            # Move to next stage: Contact Details
            state["stage"] = "COLLECTING_CONTACT"
            await self.save_state(session_id, state)

            return {
                "message": (
                    "C'est bien noté pour ces précisions techniques !\n\n"
                    "2️⃣ **À qui devons-nous adresser le devis ?**\n"
                    "Merci de m'indiquer votre **Nom / Société** ainsi que votre **Numéro de téléphone (ou WhatsApp)**."
                ),
                "session_id": session_id,
                "sales_stage": "COLLECTING_CONTACT",
            }

        # STAGE 2: Contact Information (Name & Phone/Email)
        elif stage == "COLLECTING_CONTACT":
            state["answers"]["contact_response"] = user_message.strip()

            # Attempt to parse name and contact
            if not state.get("full_name"):
                if extracted["name"]:
                    state["full_name"] = extracted["name"]
                else:
                    # If user just typed their name/company before or with phone
                    clean_name = re.sub(r'(\+?221\s?)?([783]\d{1}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}|\d{9,15})', '', user_message)
                    clean_name = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '', clean_name).strip(' ,;-')
                    if len(clean_name) >= 2:
                        state["full_name"] = clean_name
                    elif client_name and client_name.strip() and client_name.lower() not in ("user", "candidat", "client"):
                        state["full_name"] = client_name.strip()
                    else:
                        state["full_name"] = "Client"

            # Move to stage 3: Location / Email
            state["stage"] = "COLLECTING_LOCATION"
            await self.save_state(session_id, state)

            name_disp = state.get("full_name", "")
            name_ack = f"Merci {name_disp} ! " if name_disp and name_disp != "Client" else "Merci ! "

            return {
                "message": (
                    f"{name_ack}Dernière petite précision pour finaliser votre dossier :\n\n"
                    "3️⃣ **Dans quelle ville ou zone se situe votre projet (ex: Dakar, Cité Keur Gorgui, Thiès...) et quelle est votre adresse email ?**"
                ),
                "session_id": session_id,
                "sales_stage": "COLLECTING_LOCATION",
            }

        # STAGE 3: Location, Email & Final Submission
        elif stage == "COLLECTING_LOCATION":
            state["answers"]["location_response"] = user_message.strip()
            state["location"] = user_message.strip()

            # If user provided email here
            if extracted["email"] and not state.get("email"):
                state["email"] = extracted["email"]
            if extracted["phone"] and not state.get("phone_number"):
                state["phone_number"] = extracted["phone"]

            # Mark COMPLETED
            state["stage"] = "COMPLETED"
            state["completed_at"] = datetime.utcnow().isoformat()
            await self.save_state(session_id, state)

            full_name_val = state.get("full_name") or client_name or "Client"
            phone_val = state.get("phone_number")
            email_val = state.get("email")
            company_name_val = state.get("company_name")
            location_val = state.get("location")
            category_val = state.get("category") or "Devis Général"

            requirements_full = "\n".join(state.get("requirements", []))
            if not requirements_full:
                requirements_full = f"Demande de devis en {category_val}"

            # 1. Save Lead to PostgreSQL
            try:
                repo = CommercialLeadRepository()
                await repo.save_lead(
                    full_name=full_name_val,
                    requirements_summary=requirements_full,
                    phone_number=phone_val,
                    email=email_val,
                    company_name=company_name_val,
                    location=location_val,
                    service_category=category_val,
                    session_id=session_id,
                    channel=channel,
                    qualification_answers=state.get("answers"),
                )
                await repo.close()
                logger.info("sales_lead_saved_to_db", session_id=session_id, full_name=full_name_val)
            except Exception as db_err:
                logger.error("sales_lead_db_save_failed", session_id=session_id, error=str(db_err))

            # 2. Trigger asynchronous email notification to sales team
            try:
                asyncio.create_task(
                    email_service.send_sales_lead_notification(
                        full_name=full_name_val,
                        requirements_summary=requirements_full,
                        phone_number=phone_val,
                        email=email_val,
                        company_name=company_name_val,
                        location=location_val,
                        service_category=category_val,
                        channel=channel,
                        qualification_answers=state.get("answers"),
                    )
                )
                logger.info("sales_lead_email_notification_scheduled", session_id=session_id)
            except Exception as mail_err:
                logger.error("sales_lead_email_schedule_failed", session_id=session_id, error=str(mail_err))

            # 3. Final polite confirmation message to user
            company_label = settings.COMPANY_NAME or "NETSYSTEME Informatique"
            contact_phone = settings.COMPANY_CONTACT_PHONE or "+221 33 827 28 45"
            contact_email = settings.COMPANY_CONTACT_EMAIL or "contact@netsys-info.com"

            phone_confirmation = f" au **{phone_val}**" if phone_val else ""
            email_confirmation = f" ou par email à **{email_val}**" if email_val else ""

            final_reply = (
                f"✅ **Parfait ! Votre demande de devis a bien été transmise à notre équipe commerciale.**\n\n"
                f"📋 **Récapitulatif :**\n"
                f"- **Projet :** {category_val}\n"
                f"- **Détails :** {requirements_full}\n"
                f"- **Contact :** {full_name_val}{phone_confirmation}{email_confirmation}\n\n"
                f"Un conseiller commercial de **{company_label}** prendra contact avec vous sous **24h ouvrées** pour finaliser votre offre chiffrée.\n\n"
                f"Pour toute urgence, vous pouvez également joindre directement notre standard au **{contact_phone}** ou par email à **{contact_email}**.\n\n"
                "Avez-vous d'autres questions d'ici là ?"
            )

            return {
                "message": final_reply,
                "session_id": session_id,
                "sales_stage": "COMPLETED",
                "lead_data": {
                    "full_name": full_name_val,
                    "category": category_val,
                    "phone": phone_val,
                    "email": email_val,
                }
            }

        return None


sales_agent = SalesAgent()
