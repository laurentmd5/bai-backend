"""
Media download/upload utilities for WhatsApp.
"""

from typing import Optional, Dict, Any
import httpx
import os
import tempfile
import asyncio

from app.core.logging import get_logger

logger = get_logger(__name__)


class WhatsAppMediaError(Exception):
    pass


async def _get_multipart_client(access_token: str) -> httpx.AsyncClient:
    """
    Create a dedicated HTTP client for multipart uploads.
    This client has NO default Content-Type header to avoid conflicts with multipart/form-data.
    
    Args:
        access_token: WhatsApp access token
        
    Returns:
        Configured httpx AsyncClient for uploads
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=10.0,
            read=30.0,
            write=30.0,  # Longer write timeout for file uploads
            pool=10.0,
        ),
        limits=httpx.Limits(
            max_keepalive_connections=5,
            max_connections=10,
            keepalive_expiry=60.0,
        ),
        headers={
            "Authorization": f"Bearer {access_token}",
            # Intentionally NO Content-Type header - let httpx auto-generate it for multipart
        },
    )


async def download_media(
    media_id: str,
    access_token: str,
    api_version: str,
    phone_number_id: str,
    client: httpx.AsyncClient
) -> Optional[bytes]:
    """
    Download media from WhatsApp servers.
    
    Args:
        media_id: WhatsApp media ID
        access_token: WhatsApp access token
        api_version: API version (e.g. "v20.0")
        phone_number_id: Business phone number ID
        client: HTTP client
        
    Returns:
        Raw bytes of media or None
    """
    # First, get media URL
    url = f"https://graph.facebook.com/{api_version}/{media_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        # Get media metadata
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.error("media_metadata_failed", status=resp.status_code)
            return None
        
        data = resp.json()
        media_url = data.get("url")
        if not media_url:
            logger.error("media_url_missing", data=data)
            return None
        
        # Download actual media with retries
        import asyncio
        max_retries = 3
        for attempt in range(max_retries):
            try:
                media_resp = await client.get(media_url, timeout=20.0)
                if media_resp.status_code == 200:
                    logger.info("media_downloaded", media_id=media_id, size=len(media_resp.content))
                    return media_resp.content
                logger.warning("media_download_status_failed", status=media_resp.status_code, attempt=attempt+1)
            except httpx.TimeoutException as e:
                logger.warning("media_download_timeout", attempt=attempt+1, error=str(e))
            except Exception as e:
                logger.warning("media_download_error", attempt=attempt+1, error=str(e))
            
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s...
        
        logger.error("media_download_failed_all_retries", media_id=media_id)
        return None
        
    except Exception as e:
        logger.error("media_download_exception", error=str(e))
        return None


async def upload_media(
    audio_bytes: bytes,
    access_token: str,
    api_version: str,
    phone_number_id: str,
    client: httpx.AsyncClient,
    mime_type: str = "audio/mpeg"
) -> Optional[str]:
    """
    Upload audio media to WhatsApp using a dedicated multipart-safe client.
    
    Args:
        audio_bytes: Audio file bytes
        access_token: WhatsApp access token
        api_version: API version (e.g. "v25.0")
        phone_number_id: Business phone number ID
        client: HTTP client (not used - we create a dedicated one for multipart)
        mime_type: MIME type of the audio file (default: audio/mpeg)
    
    Returns:
        Media ID or None
    """
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/media?messaging_product=whatsapp"
    ext = "ogg" if "ogg" in mime_type else "mp3"
    files = {"file": (f"response.{ext}", audio_bytes, mime_type)}
    
    # Create a dedicated client for multipart uploads (no Content-Type: application/json conflict)
    upload_client = await _get_multipart_client(access_token)
    
    try:
        # This request will use the dedicated client with proper multipart handling
        # httpx will auto-generate: Content-Type: multipart/form-data; boundary=...
        resp = await upload_client.post(url, files=files)
        
        if resp.status_code != 200:
            logger.error(
                "media_upload_failed",
                status=resp.status_code,
                text=resp.text,
                url=url
            )
            return None
        
        data = resp.json()
        media_id = data.get("id")
        if media_id:
            logger.info("media_uploaded", media_id=media_id, size=len(audio_bytes))
        else:
            logger.warning("media_upload_no_id", response=data)
        return media_id
        
    except Exception as e:
        logger.error("media_upload_exception", error=str(e), error_type=type(e).__name__)
        return None
    finally:
        # Always close the dedicated client
        await upload_client.aclose()


async def send_audio_message(
    to_number: str,
    audio_id: str,
    send_message_func,
) -> Dict[str, Any]:
    """
    Send an audio message via WhatsApp.
    Uses the existing _send_message method of WhatsAppService.
    
    Args:
        to_number: Recipient phone number
        audio_id: Media ID from upload
        send_message_func: Reference to self._send_message
        
    Returns:
        API response
    """
    payload = {"audio": {"id": audio_id}}
    return await send_message_func(
        to_number=to_number,
        message_type="audio",
        payload=payload
    )


async def convert_to_ogg_opus(audio_bytes: bytes) -> bytes:
    """
    Convert audio bytes (e.g. WAV) to OGG Opus using ffmpeg.
    This format is required by WhatsApp for voice notes.
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_in:
        f_in.write(audio_bytes)
        in_path = f_in.name
        
    out_path = in_path + ".ogg"
    
    try:
        # Run ffmpeg asynchronously
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", in_path, 
            "-c:a", "libopus", "-b:a", "32k", "-vbr", "on", 
            "-compression_level", "10", out_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"ffmpeg conversion failed: {stderr.decode()}")
            return audio_bytes # Return original if it fails
            
        with open(out_path, "rb") as f_out:
            return f_out.read()
    except Exception as e:
        logger.error(f"Failed to convert audio: {e}")
        return audio_bytes
    finally:
        if os.path.exists(in_path):
            try:
                os.remove(in_path)
            except:
                pass
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except:
                pass