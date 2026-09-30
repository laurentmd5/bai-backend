"""
Unit tests for TTS speech rate configuration (1.25x speed / +25%).
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.audio.tts_service import EdgeTTSService


class TestTTSRate:
    """Tests for EdgeTTSService speaking rate."""

    def test_default_rate_is_plus_25_percent(self):
        """Default rate must be +25% (1.25x speed multiplier)."""
        assert EdgeTTSService.DEFAULT_RATE == "+25%"
        service = EdgeTTSService()
        assert service._rate == "+25%"

    @pytest.mark.asyncio
    async def test_synthesize_uses_default_rate_25_percent(self):
        """Calling synthesize without explicit rate should pass rate='+25%' to edge_tts.Communicate."""
        service = EdgeTTSService()
        
        async def mock_stream():
            yield {"type": "audio", "data": b"fake_mp3_bytes"}

        with patch("edge_tts.Communicate") as mock_communicate:
            mock_instance = MagicMock()
            mock_instance.stream = mock_stream
            mock_communicate.return_value = mock_instance

            audio = await service.synthesize("Bonjour, test de vitesse.", language="fr")

            assert audio == b"fake_mp3_bytes"
            mock_communicate.assert_called_once()
            _, kwargs = mock_communicate.call_args
            assert kwargs.get("rate") == "+25%"

    @pytest.mark.asyncio
    async def test_synthesize_explicit_rate_override(self):
        """Explicit rate parameter should override default rate."""
        service = EdgeTTSService()

        async def mock_stream():
            yield {"type": "audio", "data": b"fast_mp3_bytes"}

        with patch("edge_tts.Communicate") as mock_communicate:
            mock_instance = MagicMock()
            mock_instance.stream = mock_stream
            mock_communicate.return_value = mock_instance

            audio = await service.synthesize("Test override.", language="fr", rate="+50%")

            assert audio == b"fast_mp3_bytes"
            mock_communicate.assert_called_once()
            _, kwargs = mock_communicate.call_args
            assert kwargs.get("rate") == "+50%"

    @pytest.mark.asyncio
    async def test_synthesize_switches_to_english_voice_when_english_text(self):
        """English text must use English voice Liam even if language='fr' was requested."""
        service = EdgeTTSService()

        async def mock_stream():
            yield {"type": "audio", "data": b"english_audio"}

        with patch("edge_tts.Communicate") as mock_communicate:
            mock_instance = MagicMock()
            mock_instance.stream = mock_stream
            mock_communicate.return_value = mock_instance

            await service.synthesize(
                "Sorry, we are currently experiencing a temporary technical difficulty. Please try again.",
                language="fr"
            )

            mock_communicate.assert_called_once()
            args, _ = mock_communicate.call_args
            voice_used = args[1]
            assert voice_used == "en-CA-LiamNeural"

    @pytest.mark.asyncio
    async def test_synthesize_keeps_french_voice_when_french_text(self):
        """French text must use French voice Henri."""
        service = EdgeTTSService()

        async def mock_stream():
            yield {"type": "audio", "data": b"french_audio"}

        with patch("edge_tts.Communicate") as mock_communicate:
            mock_instance = MagicMock()
            mock_instance.stream = mock_stream
            mock_communicate.return_value = mock_instance

            await service.synthesize(
                "Désolé, nous rencontrons actuellement une difficulté technique momentanée.",
                language="fr"
            )

            mock_communicate.assert_called_once()
            args, _ = mock_communicate.call_args
            voice_used = args[1]
            assert voice_used == "fr-FR-HenriNeural"
