"""
Audio validation using ffprobe (from ffmpeg).
"""

import subprocess
import json
import tempfile
import os
from typing import Tuple, Optional

from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)


class AudioValidator:
    """
    Validate audio files using ffprobe.
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
        if len(audio_bytes) > cls.MAX_SIZE_BYTES:
            return False, f"Audio size exceeds {cls.MAX_SIZE_BYTES // (1024*1024)} MB limit"
        
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", tmp_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logger.error("ffprobe_failed", stderr=result.stderr)
                return False, "Unable to analyze audio format"
            
            data = json.loads(result.stdout)
            duration = float(data.get("format", {}).get("duration", 0))
            
            if duration > cls.MAX_DURATION_SECONDS:
                return False, f"Audio duration {duration:.1f}s exceeds {cls.MAX_DURATION_SECONDS}s limit"
            
            logger.debug("audio_validated", duration=round(duration, 2))
            return True, None
            
        except Exception as e:
            logger.error("audio_validation_exception", error=str(e))
            return False, "Audio validation failed"
        finally:
            os.unlink(tmp_path)