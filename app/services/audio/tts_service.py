"""
Edge TTS service – free, no API key required.
"""

import os
import re
import time
from typing import Optional, Dict
import edge_tts

from app.core.logging import get_logger
from app.core.config import settings
from app.core.metrics import tts_synthesis_duration_seconds

logger = get_logger(__name__)


def clean_text_for_tts(text: str) -> str:
    """
    Clean text for Text-To-Speech synthesis:
    - Remove all emojis and graphic pictograms (e.g. ✅, 📄, 📌, 🚀, 🎤, etc.)
    - Convert numbered emoji keycaps (1️⃣, 2️⃣) to natural numbers (1., 2.)
    - Strip Markdown syntax (**bold**, *italic*, ~~strike~~, `code`, # headers, > quotes)
    - Remove bullet points (- , * , • )
    - Clean up extra whitespace and newlines for natural speech cadence
    """
    if not text:
        return ""
    
    cleaned = text
    
    # 1. Convert keycap number emojis (e.g., 1️⃣ -> 1.)
    keycap_map = {
        "0️⃣": "0. ", "1️⃣": "1. ", "2️⃣": "2. ", "3️⃣": "3. ", "4️⃣": "4. ",
        "5️⃣": "5. ", "6️⃣": "6. ", "7️⃣": "7. ", "8️⃣": "8. ", "9️⃣": "9. ", "🔟": "10. "
    }
    for k, v in keycap_map.items():
        cleaned = cleaned.replace(k, v)
        
    # 2. Remove all Unicode emojis and symbols
    emoji_pattern = re.compile(
        "["
        "\U00010000-\U0010ffff"  # Supplemental symbols & pictographs, emojis
        "\u2600-\u27bf"          # Misc symbols, Dingbats (✅, ❌, ⚡, ✈️, etc.)
        "\u2300-\u23ff"          # Misc Technical (⏰, ⌛, etc.)
        "\u2b50-\u2b55"          # Stars & geometric shapes
        "\u200d\ufe0f"          # Zero width joiner, variation selector-16
        "\u2022\u2023\u25e6\u2043\u2219" # Bullets
        "]+",
        flags=re.UNICODE
    )
    cleaned = emoji_pattern.sub(" ", cleaned)
    
    # 3. Strip Markdown formatting
    # Headers (# Title -> Title)
    cleaned = re.sub(r'^\s*#+\s*', '', cleaned, flags=re.MULTILINE)
    # Bold / Italic / Strikethrough / Code (**text**, *text*, ~~text~~, _text_, `code`)
    cleaned = re.sub(r'[*_~`]+', '', cleaned)
    # Blockquotes (> Quote -> Quote)
    cleaned = re.sub(r'^\s*>\s*', '', cleaned, flags=re.MULTILINE)
    # Bullet lists (- Item -> Item)
    cleaned = re.sub(r'^\s*[-+*]\s+', '', cleaned, flags=re.MULTILINE)
    
    # 4. Normalize spacing & punctuation
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    cleaned = re.sub(r'\n+', '\n', cleaned)
    
    return cleaned.strip()


class EdgeTTSService:
    """
    Unified TTS Service using Edge TTS.
    """
    
    # Male voices
    VOICES = {
        "en": "en-NG-AbeoNeural",      # Nigerian male
        "fr": "fr-FR-HenriNeural",    # French male
    }
    
    # Default speech rate (slower)
    DEFAULT_RATE = "-20%"   # Slow down by 20%
    DEFAULT_VOLUME = "+0%"
    
    MAX_CACHE_SIZE = 100
    
    def __init__(self):
        self._cache: Dict[str, bytes] = {}
        # Allow override via environment variables
        self._voice_override = os.getenv("TTS_VOICE", "")
        self._rate = os.getenv("TTS_RATE", self.DEFAULT_RATE)
        self._volume = os.getenv("TTS_VOLUME", self.DEFAULT_VOLUME)
    
    async def synthesize(
        self,
        text: str,
        language: str = "en",
        rate: Optional[str] = None,
        volume: Optional[str] = None,
        voice: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Convert text to MP3 audio.
        
        Args:
            text: Text to speak
            language: Language code ('en' or 'fr')
            rate: Speaking rate (e.g. "-20%", "+0%")
            volume: Volume level
            voice: Specific voice name (overrides language mapping)
            
        Returns:
            Audio bytes or None.
        """
        if not text:
            return None
            
        speech_text = clean_text_for_tts(text)
        if not speech_text:
            return None
        
        # Voice selection
        if voice:
            selected_voice = voice
        elif self._voice_override:
            selected_voice = self._voice_override
        else:
            selected_voice = self.VOICES.get(language, self.VOICES["en"])
        
        # Rate and volume selection
        selected_rate = rate or self._rate
        selected_volume = volume or self._volume
        
        cache_key = f"{selected_voice}:{hash(speech_text)}:{selected_rate}:{selected_volume}"
        
        # Cache check
        if cache_key in self._cache:
            logger.debug("tts_cache_hit")
            return self._cache[cache_key]
        
        try:
            start_time = time.time()
            
            communicate = edge_tts.Communicate(
                speech_text,
                selected_voice,
                rate=selected_rate,
                volume=selected_volume
            )

            audio_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])
            
            duration = time.time() - start_time
            tts_synthesis_duration_seconds.observe(duration)
            
            if not audio_chunks:
                logger.error("tts_no_audio_chunks")
                return None
            
            audio_bytes = b"".join(audio_chunks)
            
            # Simple cache eviction
            if len(self._cache) >= self.MAX_CACHE_SIZE:
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = audio_bytes
            
            logger.info(
                "tts_synthesized",
                text_len=len(text),
                audio_size=len(audio_bytes),
                voice=selected_voice,
                rate=selected_rate,
                synthesis_time_sec=round(duration, 2)
            )
            return audio_bytes
            
        except Exception as e:
            logger.error("tts_synthesis_failed", error=str(e))
            return None


# Global singleton
tts = EdgeTTSService()
