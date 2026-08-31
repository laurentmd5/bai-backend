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
