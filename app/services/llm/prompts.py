"""
Centralized System Prompts for LLM Providers.
All company-specific content is loaded from company.yaml via company_config.
To change the bot persona: edit company.yaml -- no Python changes needed.
"""

from app.core.company_config import company


def get_system_prompt(language: str = "en") -> str:
    """
    Returns the appropriate system prompt based on language.
    Content is driven entirely by company.yaml.
    """
    return company.get_prompt(language)
