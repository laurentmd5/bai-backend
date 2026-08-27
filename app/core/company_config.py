"""
Company Configuration Loader.

Loads the company identity from company.yaml at startup.
This is the ONLY place company-specific content lives.
To switch to another company: edit company.yaml and restart.
"""

import os
from pathlib import Path
from typing import Optional
import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)


class CompanyConfig:
    """
    Singleton that loads and exposes all company-specific configuration
    from company.yaml. All text (prompts, responses) is loaded from this
    file -- no company identity is hardcoded anywhere else in the codebase.
    """

    def __init__(self, config_path: str = "company.yaml"):
        self._config_path = Path(config_path)
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        """Load and parse the company.yaml file."""
        if not self._config_path.exists():
            logger.error(
                "company_config_not_found",
                path=str(self._config_path.resolve()),
                message="company.yaml is missing. Using fallback defaults."
            )
            self._data = self._fallback_defaults()
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
            logger.info(
                "company_config_loaded",
                company=self.name,
                bot=self.bot_name,
                languages=self.supported_languages
            )
        except Exception as e:
            logger.error("company_config_load_failed", error=str(e))
            self._data = self._fallback_defaults()

    def _fallback_defaults(self) -> dict:
        """Minimal safe defaults if company.yaml is missing."""
        return {
            "company": {
                "name": "Company",
                "bot_name": "Bot",
                "tagline": "",
                "website": "",
                "support_email": "",
            },
            "languages": {"supported": ["en", "fr"], "default": "en"},
            "prompt": {
                "en": "You are a helpful assistant.\n\nCONTEXT:\n{context}\n\nHISTORY:\n{history}\n\nQUESTION: {question}\nANSWER:",
                "fr": "Tu es un assistant utile.\n\nCONTEXTE:\n{context}\n\nHISTORIQUE:\n{history}\n\nQUESTION: {question}\nREPONSE:",
            },
            "responses": {
                "greeting": {"en": "Hello! How can I help you?", "fr": "Bonjour ! Comment puis-je vous aider ?"},
                "help": {"en": "I am here to help. What would you like to know?", "fr": "Je suis la pour vous aider. Que souhaitez-vous savoir ?"},
                "fallback": {"en": "I don't have information on that.", "fr": "Je n'ai pas d'information sur ce sujet."},
                "stop": {"en": "You have been unsubscribed.", "fr": "Vous avez ete desabonne."},
                "start": {"en": "Welcome back!", "fr": "Bon retour !"},
                "error": {"en": "A technical error occurred. Please try again.", "fr": "Une erreur technique est survenue. Veuillez reessayer."},
                "hostile": {"en": "I am here to help. How can I assist you?", "fr": "Je suis la pour vous aider. Comment puis-je vous assister ?"},
            },
        }

    def _fmt(self, text: str) -> str:
        """Substitute company variables in a string without failing on unformatted placeholders."""
        if not text:
            return ""
        replacements = {
            "{company_name}": self.name,
            "{bot_name}": self.bot_name,
            "{website}": self.website,
            "{support_email}": self.support_email,
            "{support_phone}": self.phone,
            "{phone}": self.phone,
            "{whatsapp}": self.whatsapp,
            "{address}": self.address,
            "{tagline}": self.tagline,
            "{ninea}": self.ninea,
            "{rccm}": self.rccm,
        }
        for placeholder, value in replacements.items():
            text = text.replace(placeholder, value)
        return text


    @property
    def name(self) -> str:
        return self._data.get("company", {}).get("name", "Company")

    @property
    def bot_name(self) -> str:
        return self._data.get("company", {}).get("bot_name", "Bot")

    @property
    def tagline(self) -> str:
        return self._data.get("company", {}).get("tagline", "")

    @property
    def website(self) -> str:
        return self._data.get("company", {}).get("website", "")

    @property
    def support_email(self) -> str:
        return self._data.get("company", {}).get("support_email", "")

    @property
    def phone(self) -> str:
        return self._data.get("company", {}).get("support_phone", "") or self._data.get("company", {}).get("phone", "")

    @property
    def whatsapp(self) -> str:
        return self._data.get("company", {}).get("whatsapp", "")

    @property
    def address(self) -> str:
        return self._data.get("company", {}).get("address", "")

    @property
    def ninea(self) -> str:
        return self._data.get("company", {}).get("ninea", "")

    @property
    def rccm(self) -> str:
        return self._data.get("company", {}).get("rccm", "")

    @property

    def supported_languages(self) -> list:
        return self._data.get("languages", {}).get("supported", ["en"])

    @property
    def default_language(self) -> str:
        return self._data.get("languages", {}).get("default", "en")


    def get_prompt(self, language: str = "en") -> str:
        """Return the system prompt for the given language."""
        prompts = self._data.get("prompt", {})
        template = (
            prompts.get(language)
            or prompts.get(self.default_language)
            or prompts.get("en")
            or "You are a helpful assistant.\n\nCONTEXT:\n{context}\n\nHISTORY:\n{history}\n\nQUESTION: {question}\nANSWER:"
        )
        return self._fmt(template)

    def get_response(self, intent: str, language: str = "en") -> str:
        """Return the pre-built response for a given intent and language."""
        responses = self._data.get("responses", {})
        intent_data = responses.get(intent, {})

        if isinstance(intent_data, str):
            return self._fmt(intent_data)

        text = (
            intent_data.get(language)
            or intent_data.get(self.default_language)
            or intent_data.get("en")
            or f"[{intent} response not configured]"
        )
        return self._fmt(text)


# Module-level singleton
_config_path = os.getenv("COMPANY_CONFIG_PATH", "company.yaml")
company = CompanyConfig(config_path=_config_path)
