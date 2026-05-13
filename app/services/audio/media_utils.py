"""
Media download/upload utilities for WhatsApp.
"""

from typing import Optional, Dict, Any
import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class WhatsAppMediaError(Exception):
    pass


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
        
        # Download actual media
        media_resp = await client.get(media_url)
        if media_resp.status_code != 200:
            logger.error("media_download_failed", status=media_resp.status_code)
            return None
        
        logger.info("media_downloaded", media_id=media_id, size=len(media_resp.content))
        return media_resp.content
        
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
    Upload audio media to WhatsApp.
    
    Returns:
        Media ID or None
    """
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/media"
    headers = {"Authorization": f"Bearer {access_token}"}
    files = {"file": ("response.mp3", audio_bytes, mime_type)}
    
    try:
        resp = await client.post(url, headers=headers, files=files)
        if resp.status_code != 200:
            logger.error("media_upload_failed", status=resp.status_code, text=resp.text)
            return None
        
        data = resp.json()
        media_id = data.get("id")
        logger.info("media_uploaded", media_id=media_id)
        return media_id
        
    except Exception as e:
        logger.error("media_upload_exception", error=str(e))
        return None


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