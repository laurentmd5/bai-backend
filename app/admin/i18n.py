import json
import os
from functools import lru_cache

LOCALES_DIR = os.path.join(os.path.dirname(__file__), "locales")

@lru_cache(maxsize=10)
def load_translations(lang: str) -> dict:
    """Load translation file for a specific language."""
    filepath = os.path.join(LOCALES_DIR, f"{lang}.json")
    if not os.path.exists(filepath):
        # Fallback to English if not found
        filepath = os.path.join(LOCALES_DIR, "en.json")
        if not os.path.exists(filepath):
            return {}
            
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def get_translations(lang: str) -> dict:
    """Get translation dictionary for the given language."""
    return load_translations(lang)
