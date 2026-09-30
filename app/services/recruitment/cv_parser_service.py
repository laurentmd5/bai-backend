"""
CV Parser Service for Company Bot.
Extracts structured candidate information and scores alignment with company technical domains.
"""

import json
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from app.core.config import settings
from app.core.logging import get_logger
from app.services.llm.factory import get_llm_provider

logger = get_logger(__name__)

NETSYSTEME_DOMAINS = {
    "reseaux_telecoms": [
        "réseau", "reseau", "cisco", "mikrotik", "unifi", "ubiquiti", "wi-fi", "wifi",
        "routeur", "switch", "ip/mpls", "lan", "wan", "vlan", "fibre optique", "fibre",
        "tcp/ip", "routage", "commutation", "dns", "dhcp", "vpn"
    ],
    "energie_solaire": [
        "solaire", "photovoltaïque", "photovoltaique", "onduleur", "panneau", "batterie",
        "lithium", "énergie", "energie", "dimensionnement", "mppt", "victron"
    ],
    "securite_videosurveillance": [
        "caméra", "camera", "vidéosurveillance", "videosurveillance", "cctv", "hikvision",
        "dahua", "nvr", "dvr", "contrôle d'accès", "controle d'acces", "rfid", "biométrie",
        "biometrie", "alarme", "ajax", "intrusion", "sécurité électronique"
    ],
    "courant_fort_faible": [
        "câblage", "cablage", "vdi", "armoire de brassage", "baie", "tgbt", "électricité",
        "electricite", "courant fort", "courant faible", "schéma électrique", "raccordement"
    ],
    "telephonie_voip": [
        "voip", "toip", "ipbx", "pabx", "sip", "asterisk", "3cx", "grandstream", "dinstar",
        "téléphonie ip", "telephonie ip", "trunk sip"
    ],
    "securite_incendie": [
        "incendie", "centrale incendie", "détecteur de fumée", "detecteur de fumee",
        "extincteur", "extinction", "évacuation", "securité incendie"
    ],
    "domotique": [
        "domotique", "smart home", "gtb", "gtc", "interphone", "interphonie", "automatisme",
        "éclairage connecté", "eclairage connecte"
    ],
    "developpement_web": [
        "react", "next.js", "nextjs", "node.js", "nodejs", "python", "fastapi", "django",
        "javascript", "typescript", "html", "css", "postgresql", "sql", "git", "api rest",
        "docker", "fullstack", "frontend", "backend"
    ],
    "logiciels_erp": [
        "odoo", "erp", "crm", "gestion commerciale", "comptabilité", "base de données",
        "intégration erp", "workflow"
    ]
}


class CVParserService:
    """Service to parse, structure and score CV documents."""

    async def parse_cv_text(self, raw_text: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Parse raw CV text into structured profile using LLM with regex heuristics fallback.
        
        Args:
            raw_text: Extracted text from PDF or DOCX
            filename: Original CV filename
            
        Returns:
            Dict with candidate metadata, skills, field experience, and domain scores.
        """
        if not raw_text or len(raw_text.strip()) < 20:
            return self._empty_profile(filename)

        logger.info("parsing_cv_started", filename=filename, text_length=len(raw_text))

        # 1. Try extraction via LLM
        try:
            llm = get_llm_provider()
            company_label = settings.COMPANY_NAME or "l'entreprise"
            prompt = f"""Tu es un expert en recrutement technique pour {company_label}.
Analyse le CV ci-dessous et extrait TOUTES les informations clés sous format JSON strict avec les clés exactes suivantes :
{{
  "full_name": "Nom et prénom du candidat",
  "email": "Adresse email ou null",
  "phone": "Numéro de téléphone ou null",
  "education_level": "Niveau d'études (ex: Bac+2, Bac+5, Licence, Master)",
  "diploma": "Intitulé du diplôme le plus élevé",
  "technical_skills": ["Compétence 1", "Compétence 2"],
  "field_experience": ["Projet ou travail de terrain 1", "Installation 2"],
  "years_of_experience": 0.0,
  "summary": "Court résumé en 2-3 phrases des points forts du candidat pour {company_label}"
}}

Texte du CV :
\"\"\"{raw_text[:4000]}\"\"\"

Réponds UNIQUEMENT avec l'objet JSON valide, sans texte additionnel ni markdown (pas de ```json)."""

            response_str = await llm.generate_with_retry(
                prompt=prompt,
                context="",
                language="fr",
                max_retries=1
            )
            
            # Clean markdown formatting if present
            cleaned = response_str.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            parsed = json.loads(cleaned)
        except Exception as e:
            logger.warning("cv_llm_parsing_fallback", error=str(e))
            parsed = self._extract_heuristics(raw_text)

        # 2. Extract matched domains and calculate score
        matched_domains, domain_scores, match_score = self.evaluate_domain_match(raw_text, parsed)
        
        parsed["filename"] = filename or "cv.pdf"
        parsed["parsed_at"] = datetime.utcnow().isoformat()
        parsed["matched_domains"] = matched_domains
        parsed["domain_scores"] = domain_scores
        parsed["match_score"] = match_score
        parsed["raw_preview"] = raw_text[:300].strip()

        logger.info(
            "parsing_cv_completed",
            full_name=parsed.get("full_name"),
            match_score=match_score,
            matched_domains=matched_domains
        )

        return parsed

    def evaluate_domain_match(self, raw_text: str, parsed: Dict[str, Any]) -> tuple[List[str], Dict[str, float], float]:
        """
        Evaluate alignment between candidate profile and NETSYSTEME's 9 domains.
        """
        text_lower = (raw_text + " " + " ".join(parsed.get("technical_skills", []))).lower()
        
        matched_domains = []
        domain_scores = {}
        total_hits = 0

        for domain, keywords in NETSYSTEME_DOMAINS.items():
            hits = sum(1 for kw in keywords if kw in text_lower)
            if hits > 0:
                score = min(100.0, hits * 25.0)
                domain_scores[domain] = score
                matched_domains.append(domain)
                total_hits += hits

        # Base score on domain hits + experience bonus
        base_score = min(80.0, total_hits * 12.0)
        years = float(parsed.get("years_of_experience", 0.0) or 0.0)
        exp_bonus = min(20.0, years * 5.0)
        
        final_score = round(min(100.0, base_score + exp_bonus), 1)
        if not matched_domains:
            final_score = max(20.0, final_score)
            
        return matched_domains, domain_scores, final_score

    def _extract_heuristics(self, text: str) -> Dict[str, Any]:
        """Fallback regex extractor for CV text."""
        # Email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        email = email_match.group(0) if email_match else None
        
        # Phone (Supports +221 77 123 45 67, 771234567, 33 827 28 45)
        phone_match = re.search(r'(?:\+?221\s*)?(?:7[05678](?:[\s.-]?\d){7}|33(?:[\s.-]?\d){7})', text)
        phone = phone_match.group(0).strip() if phone_match else None

        # First non-empty lines as potential name
        lines = [line.strip() for line in text.split("\n") if line.strip() and not line.strip().lower().startswith(("tel", "email", "cv", "curriculum"))]
        full_name = lines[0] if lines else "Candidat"
        # If line contains separator like '-', take the first part
        if " - " in full_name:
            full_name = full_name.split(" - ")[0].strip()

        return {
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "education_level": "Non spécifié",
            "diploma": "Diplôme technique",
            "technical_skills": [],
            "field_experience": [],
            "years_of_experience": 0.0,
            "summary": "Profil technique extrait automatiquement."
        }


    def _empty_profile(self, filename: Optional[str]) -> Dict[str, Any]:
        return {
            "full_name": "Candidat",
            "filename": filename or "document",
            "email": None,
            "phone": None,
            "education_level": None,
            "diploma": None,
            "technical_skills": [],
            "field_experience": [],
            "years_of_experience": 0.0,
            "summary": "Document vide ou illisible.",
            "matched_domains": [],
            "domain_scores": {},
            "match_score": 0.0,
            "parsed_at": datetime.utcnow().isoformat()
        }


    def evaluate_questionnaire_score(
        self,
        answers: Dict[str, Any]
    ) -> Tuple[float, List[str], Dict[str, float]]:
        """
        Evaluate candidate screening questionnaire answers.
        
        Barème (Total 100 points) :
        - Q1 (15 pts) : Connaissance et validation de l'offre
        - Q2 (15 pts) : Disponibilité pour commencer
        - Q3 (25 pts) : Accord sur le cadre du stage d'évaluation
        - Q4 (25 pts) : Compétences techniques alignées avec les métiers
        - Q5 (20 pts) : Expérience de terrain / interventions pratiques
        
        Returns:
            (total_score, matched_domains, breakdown_dict)
        """
        scores: Dict[str, float] = {}
        matched_domains: List[str] = []

        # -------------------------------------------------------------
        # Q1 : Connaissance de l'offre (15 pts)
        # -------------------------------------------------------------
        q1_text = str(answers.get("q1_offer_knowledge", "")).lower().strip()
        if any(w in q1_text for w in ["oui", "parfait", "bien pris", "lu", "compris", "d'accord", "connaissance"]):
            scores["q1_offer_knowledge"] = 15.0
        elif "briefé" in q1_text or "assistant" in q1_text or "netbot" in q1_text:
            scores["q1_offer_knowledge"] = 10.0
        elif any(w in q1_text for w in ["non", "pas", "jamais"]):
            scores["q1_offer_knowledge"] = 5.0
        else:
            scores["q1_offer_knowledge"] = 10.0 if q1_text else 0.0

        # -------------------------------------------------------------
        # Q2 : Disponibilité (15 pts)
        # -------------------------------------------------------------
        q2_text = str(answers.get("q2_availability", "")).lower().strip()
        immediate_kws = [
            "immédiat", "immediat", "tout de suite", "dès maintenant", "des maintenant",
            "dès lundi", "des lundi", "maintenant", "aujourd'hui", "toujours", "libre", "disponible"
        ]
        short_term_kws = ["semaine", "mois", "bientôt", "bientot", "prochain", "jours"]
        if any(w in q2_text for w in immediate_kws):
            scores["q2_availability"] = 15.0
        elif any(w in q2_text for w in short_term_kws):
            scores["q2_availability"] = 10.0
        else:
            scores["q2_availability"] = 7.0 if q2_text else 0.0

        # -------------------------------------------------------------
        # Q3 : Accord sur les conditions (25 pts)
        # -------------------------------------------------------------
        q3_text = str(answers.get("q3_conditions_agreement", "")).lower().strip()
        agree_kws = [
            "oui", "d'accord", "dacord", "en phase", "parfait", "aucun problème",
            "aucun probleme", "aucun souci", "je valide", "valide", "compris", "ok", "d accord", "convient"
        ]
        disagree_kws = ["non", "pas d'accord", "refuse", "impossible", "pas possible"]
        if any(w in q3_text for w in disagree_kws):
            scores["q3_conditions_agreement"] = 0.0
        elif any(w in q3_text for w in agree_kws):
            scores["q3_conditions_agreement"] = 25.0
        else:
            scores["q3_conditions_agreement"] = 12.0 if q3_text else 0.0

        # -------------------------------------------------------------
        # Q4 : Compétences techniques & Domaines (25 pts)
        # -------------------------------------------------------------
        q4_text = str(answers.get("q4_technical_skills", "")).lower().strip()
        hits_count = 0
        for domain, kws in NETSYSTEME_DOMAINS.items():
            domain_hits = sum(1 for kw in kws if kw in q4_text)
            if domain_hits > 0:
                if domain not in matched_domains:
                    matched_domains.append(domain)
                hits_count += domain_hits

        if hits_count >= 3:
            scores["q4_technical_skills"] = 25.0
        elif hits_count >= 1:
            scores["q4_technical_skills"] = 18.0
        elif len(q4_text) > 10:
            scores["q4_technical_skills"] = 8.0
        else:
            scores["q4_technical_skills"] = 0.0

        # -------------------------------------------------------------
        # Q5 : Expérience terrain (20 pts)
        # -------------------------------------------------------------
        q5_text = str(answers.get("q5_field_experience", "")).lower().strip()
        is_negation_q5 = bool(re.search(r"\b(non|jamais|pas encore|aucun|aucune|pas fait|rien)\b", q5_text))
        has_positive_exp = bool(re.search(r"\b(oui|déjà|deja|j'ai fait|j'ai travaillé|plusieurs|ans|années|annees)\b", q5_text))
        
        field_high_kws = [
            "chantier", "déploiement", "deploiement", "installation", "intervention",
            "pose", "câblage", "cablage", "serveur", "armoire", "panneau",
            "caméra", "camera", "client", "site", "société", "societe", "entreprise"
        ]
        has_field_keywords = any(w in q5_text for w in field_high_kws) or ("terrain" in q5_text and not is_negation_q5)
        field_moderate_kws = ["stage", "école", "ecole", "université", "pratique", "quelques", "projets"]

        if is_negation_q5 and not has_positive_exp:
            scores["q5_field_experience"] = 5.0  # Pas d'expérience terrain
        elif has_field_keywords:
            scores["q5_field_experience"] = 20.0
        elif any(w in q5_text for w in field_moderate_kws) or has_positive_exp:
            scores["q5_field_experience"] = 12.0
        else:
            scores["q5_field_experience"] = 8.0 if q5_text else 0.0

        total_score = round(sum(scores.values()), 1)
        return total_score, matched_domains, scores

    def combine_scores(
        self,
        cv_score: Optional[float],
        questionnaire_score: float
    ) -> float:
        """
        Compute combined score :
        - If CV present: 60% CV + 40% Questionnaire
        - If no CV: 100% Questionnaire
        """
        if cv_score is not None and cv_score > 0.0:
            combined = 0.60 * cv_score + 0.40 * questionnaire_score
            return round(min(100.0, max(0.0, combined)), 1)
        return round(min(100.0, max(0.0, questionnaire_score)), 1)


cv_parser_service = CVParserService()

