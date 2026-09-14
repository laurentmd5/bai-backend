"""
Unit tests for CV Parser Service.
Tests extraction, regex heuristics, and domain scoring for NETSYSTEME.
"""

import pytest
from app.services.recruitment.cv_parser_service import cv_parser_service, NETSYSTEME_DOMAINS


class TestCVParserService:
    """Tests for CV analysis and domain scoring."""

    @pytest.mark.asyncio
    async def test_parse_empty_cv(self):
        """Empty or very short CV returns safe empty profile."""
        profile = await cv_parser_service.parse_cv_text("", filename="empty.pdf")
        assert profile["full_name"] == "Candidat"
        assert profile["match_score"] == 0.0
        assert profile["matched_domains"] == []

    @pytest.mark.asyncio
    async def test_heuristics_extraction(self):
        """Tests heuristic extraction of email and Senegalese phone number."""
        cv_text = """
        Moussa DIOP
        Email: moussa.diop@example.sn
        Tel: +221 77 123 45 67
        Technicien Réseaux & Télécoms
        Compétences: Cisco, Mikrotik, Wi-Fi 6 UniFi, Câblage VDI baie de brassage.
        Expérience: 2 ans d'installation terrain de caméras IP Hikvision et photovoltaïque solaire.
        """
        profile = await cv_parser_service.parse_cv_text(cv_text, filename="cv_moussa.pdf")
        assert "moussa.diop@example.sn" in (profile.get("email") or "")
        assert "77 123 45 67" in (profile.get("phone") or "") or "771234567" in (profile.get("phone") or "")
        assert profile["match_score"] > 40.0
        assert "reseaux_telecoms" in profile["matched_domains"]
        assert "securite_videosurveillance" in profile["matched_domains"]

    def test_evaluate_domain_match_solar(self):
        """Tests domain scoring on solar energy profile."""
        raw_text = "Installateur solaire photovoltaïque, dimensionnement onduleur Victron et batterie lithium"
        parsed = {"technical_skills": ["énergie solaire", "photovoltaïque", "batteries"], "years_of_experience": 3.0}
        domains, scores, total_score = cv_parser_service.evaluate_domain_match(raw_text, parsed)
        assert "energie_solaire" in domains
        assert total_score >= 35.0

    def test_evaluate_questionnaire_score_high(self):
        """Tests questionnaire scoring for an ideal candidate profile."""
        answers = {
            "q1_offer_knowledge": "Oui, parfaitement pris connaissance de l'offre.",
            "q2_availability": "Je suis disponible immédiatement dès lundi.",
            "q3_conditions_agreement": "Oui, je valide totalement les conditions et je suis en phase.",
            "q4_technical_skills": "Réseaux IP Cisco, Mikrotik, Wi-Fi 6 UniFi, Câblage VDI, Solaire.",
            "q5_field_experience": "Oui, 3 ans de travaux de terrain sur chantiers de déploiement et d'installation."
        }
        score, domains, breakdown = cv_parser_service.evaluate_questionnaire_score(answers)
        assert score >= 90.0
        assert breakdown["q1_offer_knowledge"] == 15.0
        assert breakdown["q2_availability"] == 15.0
        assert breakdown["q3_conditions_agreement"] == 25.0
        assert breakdown["q4_technical_skills"] == 25.0
        assert breakdown["q5_field_experience"] == 20.0
        assert "reseaux_telecoms" in domains

    def test_evaluate_questionnaire_score_disagreement(self):
        """Tests that disagreement on stage terms significantly reduces score."""
        answers = {
            "q1_offer_knowledge": "Oui",
            "q2_availability": "Immédiat",
            "q3_conditions_agreement": "Non, pas d'accord, je veux être payé dès le premier jour",
            "q4_technical_skills": "Informatique générale",
            "q5_field_experience": "Non, jamais fait de terrain"
        }
        score, domains, breakdown = cv_parser_service.evaluate_questionnaire_score(answers)
        assert breakdown["q3_conditions_agreement"] == 0.0
        assert score < 50.0

    def test_combine_scores_with_and_without_cv(self):
        """Tests 60/40 weighting with CV and 100% questionnaire without CV."""
        # With CV (e.g. CV=80, Questionnaire=90) -> 0.60*80 + 0.40*90 = 48 + 36 = 84.0
        combined = cv_parser_service.combine_scores(80.0, 90.0)
        assert combined == 84.0

        # Without CV (cv_score is None or 0) -> 100% of questionnaire
        assert cv_parser_service.combine_scores(None, 85.0) == 85.0
        assert cv_parser_service.combine_scores(0.0, 75.0) == 75.0
