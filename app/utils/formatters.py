"""
Response formatters for BARROW.AI.
Handles formatting of chatbot responses for different channels.
"""

from app.utils.constants import SLOGAN, MAX_WHATSAPP_MESSAGE_LENGTH


def ensure_slogan(text: str) -> str:
    """
    Ensure the NPP slogan is present at the end of the response.
    
    Args:
        text: Response text
        
    Returns:
        Text with slogan appended if missing
    """
    if SLOGAN not in text:
        return text.rstrip() + "\n\n" + SLOGAN
    return text


def truncate_for_whatsapp(text: str) -> str:
    """
    Truncate text for WhatsApp (4096 char limit) while preserving the slogan.
    
    Args:
        text: Full response text
        
    Returns:
        Truncated text with slogan
    """
    if len(text) <= MAX_WHATSAPP_MESSAGE_LENGTH:
        return text
    
    max_len = MAX_WHATSAPP_MESSAGE_LENGTH - len(SLOGAN) - 5
    truncated = text[:max_len]
    
    # Try to cut at last sentence
    for punct in ['.', '!', '?']:
        last_punct = truncated.rfind(punct)
        if last_punct > max_len * 0.7:
            truncated = truncated[:last_punct + 1]
            break
    
    return truncated + "\n\n" + SLOGAN


def format_sources(sources: list) -> str:
    """
    Format source documents for display.
    
    Args:
        sources: List of source dicts
        
    Returns:
        Formatted source string
    """
    if not sources:
        return ""
    
    parts = []
    for s in sources[:3]:
        doc = s.get("document", "Unknown")
        section = s.get("section", "")
        relevance = s.get("relevance", 0)
        
        if section:
            parts.append(f"[Source: {doc}, {section}] (relevance: {relevance:.0%})")
        else:
            parts.append(f"[Source: {doc}] (relevance: {relevance:.0%})")
    
    return " | ".join(parts)


def mask_phone_number(phone: str) -> str:
    """
    Mask phone number for logging/display.
    
    Args:
        phone: Full phone number
        
    Returns:
        Masked phone (shows last 4 digits)
    """
    if not phone or len(phone) < 4:
        return "***"
    return f"***{phone[-4:]}"


def sanitize_for_log(text: str, max_length: int = 100) -> str:
    """
    Truncate text for safe logging.
    
    Args:
        text: Text to sanitize
        max_length: Maximum length
        
    Returns:
        Truncated text
    """
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."