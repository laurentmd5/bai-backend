"""
Input sanitizers for Company Bot.
Re-exports from core security module to avoid duplication.
"""

from app.core.security import (
    sanitize_input,
    html_escape,
    detect_xss,
    detect_prompt_injection,
    detect_sql_injection,
    detect_hostile_content,
)

__all__ = [
    "sanitize_input",
    "html_escape",
    "detect_xss",
    "detect_prompt_injection",
    "detect_sql_injection",
    "detect_hostile_content",
]
