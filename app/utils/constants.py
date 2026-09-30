"""
Application-wide constants for Company Bot.
Central place for all hardcoded values.
"""

# =============================================================================
# BRANDING
# =============================================================================
SLOGAN = ""  # Set via company.yaml
APP_URL = ""  # Set via company.yaml
PACE_CONTACT = "contact the nearest PACE office"

# =============================================================================
# LANGUAGES
# =============================================================================
SUPPORTED_LANGUAGES = {"en", "fr"}  # Configured in company.yaml
DEFAULT_LANGUAGE = "en"

# =============================================================================
# CHANNELS
# =============================================================================
CHANNEL_WEB = "web"
CHANNEL_WHATSAPP = "whatsapp"

# =============================================================================
# LIMITS
# =============================================================================
MAX_MESSAGE_LENGTH = 2000
MIN_MESSAGE_LENGTH = 1
MAX_WHATSAPP_MESSAGE_LENGTH = 4000
MAX_RESPONSE_TOKENS = 512

# =============================================================================
# RAG
# =============================================================================
DEFAULT_TOP_K = 5
DEFAULT_SIMILARITY_THRESHOLD = 0.70
DEFAULT_CHUNK_SIZE = 400
DEFAULT_CHUNK_OVERLAP = 80

# =============================================================================
# FALLBACK MESSAGES
# =============================================================================
FALLBACK_NOT_FOUND_EN = ""  # Set via company.yaml
FALLBACK_NOT_FOUND_FR = ""  # Set via company.yaml
FALLBACK_TECHNICAL_EN = "I am experiencing a temporary technical issue. Please try again in a few moments."
FALLBACK_TECHNICAL_FR = "Je rencontre une difficulté technique momentanée. Veuillez réessayer dans quelques instants."


