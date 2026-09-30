"""
Tests unitaires pour le module CompanyConfig (Multi-Entreprise).
Verifie le chargement de company.yaml, la gestion des langues,
des prompts et des reponses pre-construites.
"""

import os
import tempfile
import pytest
import yaml

from app.core.company_config import CompanyConfig, company


class TestCompanyConfig:
    """Tests du chargeur de configuration d'entreprise."""

    def test_global_company_singleton_loaded(self):
        """Le singleton global est correctement charge."""
        assert company is not None
        assert "NETSYSTEME" in company.name
        assert company.bot_name == "NetBot"
        assert "en" in company.supported_languages
        assert "fr" in company.supported_languages
        assert company.default_language == "fr"

    def test_company_properties(self):
        """Verification des proprietes de base de l'entreprise."""
        assert company.name == "NETSYSTEME INFORMATIQUE"
        assert company.bot_name == "NetBot"
        assert company.website == "https://netsys-info.com"
        assert company.support_email == "contact@netsys-info.com"
        assert company.phone == "+221 33 827 28 45"
        assert company.whatsapp == "+221 77 846 16 55"
        assert "Cité Keur Gorgui" in company.address
        assert "Votre partenaire IT" in company.tagline

    def test_get_prompt_french(self):
        """Le prompt en francais est correctement formate avec les variables."""
        prompt = company.get_prompt("fr")
        assert "NetBot" in prompt
        assert "NETSYSTEME" in prompt
        assert "{context}" in prompt
        assert "{history}" in prompt
        assert "{question}" in prompt

    def test_get_prompt_english(self):
        """Le prompt en anglais est correctement formate."""
        prompt = company.get_prompt("en")
        assert "NetBot" in prompt
        assert "NETSYSTEME" in prompt
        assert "{context}" in prompt
        assert "{question}" in prompt

    def test_get_prompt_unsupported_language_fallback(self):
        """Une langue inconnue retombe sur la langue par defaut ou l'anglais."""
        prompt = company.get_prompt("de")
        assert prompt is not None
        assert len(prompt) > 0
        assert "NETSYSTEME" in prompt

    def test_get_response_greeting_french(self):
        """Reponse greeting en francais."""
        resp = company.get_response("greeting", "fr")
        assert "Bonjour" in resp
        assert "NETSYSTEME" in resp
        assert "NetBot" in resp

    def test_get_response_greeting_english(self):
        """Reponse greeting en anglais."""
        resp = company.get_response("greeting", "en")
        assert "Hello" in resp
        assert "NETSYSTEME" in resp

    def test_get_response_help(self):
        """Reponse help par langue."""
        help_fr = company.get_response("help", "fr")
        assert "NetBot" in help_fr
        assert "NETSYSTEME" in help_fr
        assert "33 827 28 45" in help_fr

        help_en = company.get_response("help", "en")
        assert "NetBot" in help_en

    def test_get_response_fallback(self):
        """Reponse fallback par langue."""
        fb_fr = company.get_response("fallback", "fr")
        assert "contact@netsys-info.com" in fb_fr or "https://netsys-info.com" in fb_fr

    def test_get_response_stop_and_start(self):
        """Reponses de desabonnement et reabonnement."""
        stop_fr = company.get_response("stop", "fr")
        assert "désabonné" in stop_fr or "desabonne" in stop_fr

        start_fr = company.get_response("start", "fr")
        assert "abonné" in start_fr or "abonne" in start_fr


    def test_custom_yaml_loading(self):
        """Test du chargement d'un fichier YAML d'une toute autre entreprise."""
        custom_data = {
            "company": {
                "name": "ACME Corp",
                "bot_name": "AcmeBot",
                "tagline": "Quality everywhere",
                "website": "https://acme.example.com",
                "support_email": "help@acme.example.com",
            },
            "languages": {
                "supported": ["en"],
                "default": "en"
            },
            "prompt": {
                "en": "You are {bot_name} for {company_name}.\n{context}\n{history}\n{question}"
            },
            "responses": {
                "greeting": {
                    "en": "Welcome to {company_name}! I am {bot_name}."
                },
                "help": {
                    "en": "Contact {support_email}."
                }
            }
        }

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.safe_dump(custom_data, f)
            temp_path = f.name

        try:
            cfg = CompanyConfig(config_path=temp_path)
            assert cfg.name == "ACME Corp"
            assert cfg.bot_name == "AcmeBot"
            assert cfg.supported_languages == ["en"]
            assert cfg.get_response("greeting", "en") == "Welcome to ACME Corp! I am AcmeBot."
            assert cfg.get_response("help", "en") == "Contact help@acme.example.com."
            prompt = cfg.get_prompt("en")
            assert "AcmeBot for ACME Corp" in prompt
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_missing_yaml_fallback_defaults(self):
        """Si le fichier n'existe pas, des valeurs de secours sont utilisees sans crasher."""
        cfg = CompanyConfig(config_path="non_existent_file_12345.yaml")
        assert cfg.name == "Company"
        assert cfg.bot_name == "Bot"
        assert len(cfg.get_prompt("en")) > 0
        assert len(cfg.get_response("greeting", "en")) > 0
