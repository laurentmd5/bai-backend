"""
CV Parser Service for Company Bot.
Extracts structured candidate information and scores alignment with NETSYSTEME domains.
"""

import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

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
            prompt = f"""Tu es un expert en recrutement technique pour l'entreprise NETSYSTEME INFORMATIQUE.
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
  "summary": "Court résumé en 2-3 phrases des points forts du candidat pour NETSYSTEME"
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


cv_parser_service = CVParserService()
