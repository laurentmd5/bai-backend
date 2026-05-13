"""
Audio validation using pydub + ffmpeg.
Checks format, duration, size.
"""

import io
from typing import Tuple, Optional

from pydub import AudioSegment

from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)


class AudioValidator:
    """
    Validate audio files from WhatsApp before transcription.
    """
    
    MAX_DURATION_SECONDS = getattr(settings, "MAX_AUDIO_DURATION_SECONDS", 180)  # 3 minutes
    MAX_SIZE_BYTES = 16 * 1024 * 1024  # WhatsApp limit 16 MB
    
    @classmethod
    def validate(cls, audio_bytes: bytes) -> Tuple[bool, Optional[str]]:
        """
        Validate audio bytes.
        
        Returns:
            (is_valid, error_message)
        """
        # Check size
        if len(audio_bytes) > cls.MAX_SIZE_BYTES:
            return False, f"Audio size exceeds {cls.MAX_SIZE_BYTES // (1024*1024)} MB limit"
        
        # Check format and duration using pydub
        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
            duration_seconds = len(audio) / 1000.0
            
            if duration_seconds > cls.MAX_DURATION_SECONDS:
                return False, f"Audio duration {duration_seconds:.1f}s exceeds {cls.MAX_DURATION_SECONDS}s limit"
            
            # Log metadata
            logger.debug(
                "audio_validated",
                duration_sec=round(duration_seconds, 2),
                channels=audio.channels,
                frame_rate=audio.frame_rate,
                sample_width=audio.sample_width
            )
            
            return True, None
            
        except Exception as e:
            logger.error("audio_validation_failed", error=str(e))
            return False, "Audio format not supported or corrupted"