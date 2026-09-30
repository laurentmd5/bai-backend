"""
Unit tests for Whisper Groq Cloud STT optimization and non-blocking local fallback.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.audio.whisper_service import WhisperTranscriber, PHONETIC_CORRECTIONS


@pytest.fixture
def transcriber():
    """Create a WhisperTranscriber instance with fresh mocks."""
    with patch("app.services.audio.whisper_service.settings") as mock_settings:
        mock_settings.WHISPER_MODEL_SIZE = "large-v3-turbo"
        mock_settings.GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"
        mock_settings.WHISPER_BEAM_SIZE = 1
        mock_settings.WHISPER_USE_GROQ = True
        mock_settings.GROQ_API_KEY = MagicMock()
        mock_settings.GROQ_API_KEY.get_secret_value.return_value = "gsk_dummy_test_key"
        mock_settings.AUDIO_CACHE_TTL_SECONDS = 86400
        
        transcriber = WhisperTranscriber()
        return transcriber


@pytest.mark.asyncio
async def test_whisper_groq_success(transcriber):
    """Verify that Groq Whisper is called and returns formatted text and language."""
    mock_groq_client = MagicMock()
    mock_transcription = MagicMock()
    mock_transcription.text = "Bonjour, je cherche une solution de net-systeme."
    mock_transcription.language = "fr"
    
    mock_groq_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcription)
    transcriber._groq_client = mock_groq_client

    audio_bytes = b"fake_audio_bytes_123"

    with patch("app.services.audio.whisper_service.cache_service") as mock_cache:
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        text, lang = await transcriber.transcribe_detect(audio_bytes)

        # Verification
        assert text == "Bonjour, je cherche une solution de NETSYSTEME."
        assert lang == "fr"
        mock_groq_client.audio.transcriptions.create.assert_awaited_once()
        mock_cache.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_whisper_fallback_to_local_on_groq_failure(transcriber):
    """Verify that if Groq fails, transcription falls back seamlessly to local whisper."""
    mock_groq_client = MagicMock()
    mock_groq_client.audio.transcriptions.create = AsyncMock(side_effect=Exception("Groq API Timeout"))
    transcriber._groq_client = mock_groq_client

    # Mock local model
    mock_segment = MagicMock()
    mock_segment.text = "Message transcrit en local par netsystem"
    mock_info = MagicMock()
    mock_info.language = "fr"
    mock_info.language_probability = 0.98

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], mock_info)
    transcriber._model = mock_model

    audio_bytes = b"fake_audio_bytes_fallback"

    with patch("app.services.audio.whisper_service.cache_service") as mock_cache:
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        text, lang = await transcriber.transcribe_detect(audio_bytes)

        assert text == "Message transcrit en local par NETSYSTEME"
        assert lang == "fr"
        mock_groq_client.audio.transcriptions.create.assert_awaited_once()
        mock_model.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_whisper_local_runs_in_thread(transcriber):
    """Verify that local transcription uses asyncio.to_thread to avoid blocking the event loop."""
    transcriber._groq_client = None  # No Groq available

    audio_bytes = b"fake_audio_thread_check"

    with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
        mock_to_thread.return_value = ("Test en thread", "fr", 0.99)
        with patch("app.services.audio.whisper_service.cache_service") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()

            text, lang = await transcriber.transcribe_detect(audio_bytes)

            assert text == "Test en thread"
            assert lang == "fr"
            mock_to_thread.assert_awaited_once()


@pytest.mark.asyncio
async def test_whisper_cache_hit_bypasses_all_models(transcriber):
    """Verify that a Redis cache hit returns immediately without calling Groq or local model."""
    mock_groq_client = MagicMock()
    mock_groq_client.audio.transcriptions.create = AsyncMock()
    transcriber._groq_client = mock_groq_client

    mock_model = MagicMock()
    transcriber._model = mock_model

    audio_bytes = b"cached_audio_content"

    with patch("app.services.audio.whisper_service.cache_service") as mock_cache:
        mock_cache.get = AsyncMock(return_value={"text": "Texte mis en cache", "lang": "fr"})

        text, lang = await transcriber.transcribe_detect(audio_bytes)

        assert text == "Texte mis en cache"
        assert lang == "fr"
        mock_groq_client.audio.transcriptions.create.assert_not_called()
        mock_model.transcribe.assert_not_called()


def test_post_process_phonetic_corrections(transcriber):
    """Verify phonetic corrections for company name."""
    for wrong, expected in PHONETIC_CORRECTIONS.items():
        input_text = f"Bienvenue chez {wrong} aujourd'hui"
        res, _ = transcriber._post_process(input_text, "fr")
        assert expected in res
