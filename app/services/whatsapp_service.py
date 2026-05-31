"""
WhatsApp Service for BARROW.AI.
Integrates with Meta WhatsApp Cloud API for bidirectional messaging.
"""

import asyncio
import hashlib
import hmac
import json
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import BarrowAIException, ErrorCode
from app.core.metrics import whatsapp_messages_received_total, voice_message_processed_total
from app.services.cache.redis_cache import cache_service, CacheNamespace
from app.services.chat_service import ChatService
from app.services.validation.input_validator import InputValidator
from app.services.validation.security_validator import SecurityValidator
from app.services.audio.audio_validator import AudioValidator
from app.services.audio.media_utils import download_media, upload_media, send_audio_message
from app.services.audio.whisper_service import whisper
from app.services.audio.tts_service import tts
from app.repositories.session_repository import SessionRepository
from app.models.request.whatsapp import WhatsAppWebhookRequest, WhatsAppMessage

logger = get_logger(__name__)


class WhatsAppException(BarrowAIException):
    """WhatsApp-specific exception."""
    
    def __init__(self, message: str, code: Optional[int] = None, original_error: Optional[Exception] = None):
        super().__init__(
            message=f"WhatsApp API error: {message}",
            code=ErrorCode.WHATSAPP_SEND_FAILED if code else ErrorCode.INTERNAL_ERROR,
            status_code=503,
            details={
                "provider": "whatsapp",
                "api_code": code,
                "original_error": str(original_error) if original_error else None
            }
        )
        self.whatsapp_code = code


class WhatsAppRateLimitException(WhatsAppException):
    """Raised when WhatsApp rate limit is hit."""
    
    def __init__(self, retry_after: Optional[int] = None):
        super().__init__(
            message="WhatsApp rate limit exceeded",
            code=130429
        )
        self.retry_after = retry_after


class WhatsAppInvalidPhoneException(WhatsAppException):
    """Raised when phone number is invalid."""
    
    def __init__(self, phone_number: str):
        super().__init__(
            message=f"Invalid phone number: {phone_number}",
            code=131047
        )


class WhatsAppService:
    """
    WhatsApp Cloud API service for BARROW.AI.
    
    Handles:
    - Webhook verification
    - Incoming message processing
    - Outgoing message sending
    - Media message handling
    - Template messages
    - Opt-out management
    - Rate limiting compliance
    """
    
    # WhatsApp Cloud API base URL
    BASE_URL = "https://graph.facebook.com"
    
    # Message type handlers
    SUPPORTED_MESSAGE_TYPES = {"text", "image", "video", "audio", "document", "location", "interactive", "button"}
    
    # Maximum message length for WhatsApp
    MAX_MESSAGE_LENGTH = 4000
    
    # Rate limit: messages per second (Meta limit is 80, we're conservative)
    RATE_LIMIT_PER_SECOND = 50
    
    def __init__(
        self,
        chat_service: ChatService,
        session_repository: SessionRepository,
    ):
        """
        Initialize WhatsApp service.
        
        Args:
            chat_service: Main chat service for processing messages
            session_repository: Repository for session management
        """
        self._chat_service = chat_service
        self._session_repo = session_repository
        self._input_validator = InputValidator()
        self._security_validator = SecurityValidator()
        
        # API credentials
        self._phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self._access_token = settings.WHATSAPP_ACCESS_TOKEN.get_secret_value()
        self._verify_token = settings.WHATSAPP_VERIFY_TOKEN.get_secret_value()
        self._app_secret = settings.WHATSAPP_APP_SECRET.get_secret_value()
        self._api_version = settings.WHATSAPP_API_VERSION
        self._business_account_id = settings.WHATSAPP_BUSINESS_ACCOUNT_ID
        
        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None
        
        # Rate limiting
        self._message_semaphore = asyncio.Semaphore(self.RATE_LIMIT_PER_SECOND)
    
    async def _get_client(self) -> httpx.AsyncClient:
        """
        Get or create HTTP client with connection pooling.
        
        Returns:
            Configured httpx AsyncClient
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=30.0,
                    write=10.0,
                    pool=10.0,
                ),
                limits=httpx.Limits(
                    max_keepalive_connections=20,
                    max_connections=50,
                    keepalive_expiry=60.0,
                ),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._access_token}",
                },
            )
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    def verify_webhook(
        self,
        mode: str,
        challenge: str,
        verify_token: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify WhatsApp webhook during initial setup.
        
        Args:
            mode: Hub mode (should be "subscribe")
            challenge: Hub challenge to echo back
            verify_token: Token to verify
            
        Returns:
            Tuple of (verified, challenge or error)
        """
        if mode != "subscribe":
            logger.warning("whatsapp_webhook_verify_invalid_mode", mode=mode)
            return False, None
        
        if verify_token != self._verify_token:
            logger.warning("whatsapp_webhook_verify_invalid_token")
            return False, None
        
        logger.info("whatsapp_webhook_verified_successfully")
        return True, challenge
    
    def _validate_signature(self, signature: str, payload: bytes) -> bool:
        """
        BUG #1 FIX: Validate WhatsApp webhook POST signature with App Secret.
        
        Note: verify_token is for GET webhook verification only.
        POST webhooks must use App Secret from Meta Developer Console.
        
        Args:
            signature: X-Hub-Signature-256 header
            payload: Raw request body
            
        Returns:
            True if signature is valid
        """
        if not signature or not signature.startswith("sha256="):
            return False
        
        expected_signature = signature[7:]  # Remove "sha256=" prefix
        
        # ✅ CORRECT: Use App Secret for POST signature validation
        computed_signature = hmac.new(
            key=self._app_secret.encode(),
            msg=payload,
            digestmod=hashlib.sha256,
        ).hexdigest()
        
        return hmac.compare_digest(computed_signature, expected_signature)
    
    async def process_webhook(
        self,
        payload: Dict[str, Any],
        raw_body: bytes,
        signature: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process incoming WhatsApp webhook.
        
        Args:
            payload: Parsed JSON payload
            raw_body: Raw request body for signature validation
            signature: X-Hub-Signature-256 header
            
        Returns:
            Processing result
        """
        # Validate signature if provided
        if signature and not self._validate_signature(signature, raw_body):
            logger.warning("whatsapp_webhook_invalid_signature")
            return {"status": "error", "reason": "invalid_signature"}
        
        try:
            webhook_request = WhatsAppWebhookRequest(**payload)
        except Exception as e:
            logger.error("whatsapp_webhook_parse_error", error=str(e))
            return {"status": "error", "reason": "parse_error", "error": str(e)}
        
        if not webhook_request.has_messages():
            # Could be status updates, we can ignore for POC
            logger.debug("whatsapp_webhook_no_messages")
            return {"status": "ignored", "reason": "no_messages"}
        
        messages = webhook_request.get_messages()
        processed_count = 0
        errors = []
        
        for message in messages:
            try:
                await self._process_incoming_message(message)
                processed_count += 1
            except Exception as e:
                logger.error("whatsapp_message_processing_failed", error=str(e), message_id=message.id)
                errors.append({"message_id": message.id, "error": str(e)})
        
        return {
            "status": "success",
            "processed": processed_count,
            "total": len(messages),
            "errors": errors if errors else None,
        }
    
    async def _process_incoming_message(self, message: WhatsAppMessage) -> None:
        """
        Process a single incoming WhatsApp message.
        
        Args:
            message: Parsed WhatsApp message
        """
        phone_number = message.phone_number
        message_id = message.message_id
        
        # Idempotency check
        if await cache_service.is_whatsapp_processed(message_id):
            logger.debug("whatsapp_message_already_processed", message_id=message_id)
            return
        
        # Mark as processed immediately
        await cache_service.mark_whatsapp_processed(message_id, ttl=3600)
        
        # Check rate limit
        allowed, remaining, reset_in = await self._security_validator.check_whatsapp_rate_limit(
            phone_number=phone_number,
        )
        
        if not allowed:
            logger.warning(
                "whatsapp_rate_limit_exceeded",
                phone=phone_number[-4:],
                reset_in=reset_in,
            )
            await self.send_text_message(
                to_number=phone_number,
                text="You are sending messages too quickly. Please wait a moment.",
            )
            return
        
        # Check opt-out status
        if await cache_service.is_opted_out(phone_number):
            logger.debug("whatsapp_user_opted_out", phone=phone_number[-4:])
            return
        
        # Handle STOP command
        if message.is_text and message.text_content:
            text = message.text_content.strip().upper()
            
            if text == "STOP" or text == "UNSUBSCRIBE":
                await self._handle_stop_command(phone_number)
                return
            
            if text == "START" or text == "SUBSCRIBE":
                await self._handle_start_command(phone_number)
                return
        
        # Handle voice / audio messages
        if message.type == "audio" or (hasattr(message, 'audio') and message.audio):
            whatsapp_messages_received_total.labels(type="voice").inc()
            await self._handle_voice_message(message, phone_number)
            return
        
        # Only process text messages for now (POC)
        if not message.is_text or not message.text_content:
            whatsapp_messages_received_total.labels(type="other").inc()
            await self.send_text_message(
                to_number=phone_number,
                text="I can only process text or voice messages at the moment. Please send a voice note or type your question.",
            )
            return
        
        # Record text message
        whatsapp_messages_received_total.labels(type="text").inc()
        
        user_message = message.text_content

        # Detect language from the user's own text
        detected_language = self._input_validator.detect_language(user_message)
        logger.info(
            "whatsapp_text_language_detected",
            phone=phone_number[-4:],
            language=detected_language,
        )

        # Validate input
        try:
            is_valid, sanitized_message, _ = self._input_validator.validate_chat_message(
                message=user_message,
                language=detected_language,
                channel="whatsapp",
            )
        except Exception as e:
            logger.warning("whatsapp_input_validation_failed", error=str(e))
            await self.send_text_message(
                to_number=phone_number,
                text="I couldn't process that message. Please try again with a different question.",
            )
            return

        # Process through chat service with the detected language
        response = await self._chat_service.process_message(
            message=sanitized_message,
            session_id=None,  # Will be created/retrieved based on phone
            language=detected_language,
            channel="whatsapp",
            ip_address=None,
            user_agent="WhatsApp",
            metadata={"phone_number": phone_number, "detected_language": detected_language},
        )
        
        # Send response
        response_text = response.get("message", "")
        
        # Truncate if needed
        if len(response_text) > self.MAX_MESSAGE_LENGTH:
            response_text = self._truncate_for_whatsapp(response_text)
        
        await self.send_text_message(
            to_number=phone_number,
            text=response_text,
        )
        
        logger.info(
            "whatsapp_message_processed",
            phone=phone_number[-4:],
            response_length=len(response_text),
        )
    
    async def _handle_stop_command(self, phone_number: str) -> None:
        """
        Handle STOP command for opt-out.
        
        Args:
            phone_number: User's phone number
        """
        # Add to opt-out set
        await cache_service.add_opt_out(phone_number)
        
        # Update session if exists
        session = await self._session_repo.get_by_external_id(phone_number, "whatsapp")
        if session:
            await self._session_repo.opt_out_session(session.id)
        
        # Send confirmation
        await self.send_text_message(
            to_number=phone_number,
            text=(
                "You have been unsubscribed from AskBarrow.ai messages. "
                "You can restart the conversation anytime by sending 'START'.\n\n"
                "Ask. Know. Decide. - One Gambia. One People. One Barrow."
            ),
        )
        
        logger.info("whatsapp_user_opted_out", phone=phone_number[-4:])
    
    async def _handle_start_command(self, phone_number: str) -> None:
        """
        Handle START command for opt-in.
        
        Args:
            phone_number: User's phone number
        """
        # Remove from opt-out set
        await cache_service.remove_opt_out(phone_number)
        
        # Update session if exists
        session = await self._session_repo.get_by_external_id(phone_number, "whatsapp")
        if session:
            await self._session_repo.opt_in_session(session.id)
        
        # Send welcome back
        await self.send_text_message(
            to_number=phone_number,
            text=(
                "Welcome back to AskBarrow.ai! You are now resubscribed. "
                "How can I help you today?\n\n"
                "Ask. Know. Decide. - One Gambia. One People. One Barrow."
            ),
        )
        
        logger.info("whatsapp_user_opted_in", phone=phone_number[-4:])
    
    async def _handle_voice_message(self, message: WhatsAppMessage, phone_number: str) -> None:
        """Process an incoming voice message."""
        media_id = None
        if message.audio and message.audio.id:
            media_id = message.audio.id
        else:
            await self.send_text_message(
                to_number=phone_number,
                text="I received an audio message but no media ID. Please try again."
            )
            return
        
        # Send "processing" indicator
        await self.send_text_message(
            to_number=phone_number,
            text="🎤 I'm listening to your voice message / J'écoute votre message vocal. Please wait / Veuillez patienter..."
        )
        
        # Download media
        client = await self._get_client()
        audio_bytes = await download_media(
            media_id=media_id,
            access_token=self._access_token,
            api_version=self._api_version,
            phone_number_id=self._phone_number_id,
            client=client
        )
        
        if not audio_bytes:
            await self.send_text_message(
                to_number=phone_number,
                text="I couldn't download your voice message. Please try again."
            )
            return
        
        # Validate audio
        is_valid, error_msg = AudioValidator.validate(audio_bytes)
        if not is_valid:
            await self.send_text_message(
                to_number=phone_number,
                text=f"Your voice message could not be processed: {error_msg}. Please try a shorter message or type your question."
            )
            return
        
        # Transcribe with automatic language detection
        # whisper.transcribe_detect() passes language=None to Whisper so it
        # identifies the spoken language itself, then we confirm with our
        # text-based detector for better accuracy on short utterances.
        transcribed_text, whisper_lang = await whisper.transcribe_detect(audio_bytes)
        if not transcribed_text:
            voice_message_processed_total.labels(status="transcription_failed").inc()
            await self.send_text_message(
                to_number=phone_number,
                text="I couldn't understand your voice message. Could you please repeat or type your question?"
            )
            return

        # Refine language detection: use text-based detector to confirm/override
        # Whisper's detection (more reliable on short clips or accented speech).
        text_lang = self._input_validator.detect_language(transcribed_text)
        # Prefer text-based detection; fall back to Whisper if text is too short
        detected_language = text_lang if len(transcribed_text.split()) >= 3 else whisper_lang
        logger.info(
            "whatsapp_voice_language_detected",
            phone=phone_number[-4:],
            whisper_lang=whisper_lang,
            text_lang=text_lang,
            final_lang=detected_language,
        )

        # Validate
        try:
            is_valid, sanitized_message, _ = self._input_validator.validate_chat_message(
                message=transcribed_text,
                language=detected_language,
                channel="whatsapp",
            )
        except Exception as e:
            logger.warning("voice_input_validation_failed", error=str(e))
            await self.send_text_message(
                to_number=phone_number,
                text="I had trouble understanding your message. Could you try again?"
            )
            return

        response = await self._chat_service.process_message(
            message=sanitized_message,
            session_id=None,
            language=detected_language,
            channel="whatsapp",
            ip_address=None,
            user_agent="WhatsApp",
            metadata={
                "phone_number": phone_number,
                "is_voice": True,
                "detected_language": detected_language,
            },
        )

        response_text = response.get("message", "")
        if not response_text:
            response_text = "I'm not sure how to answer that. Please try again." if detected_language == "en" \
                else "Je ne suis pas sûr de pouvoir répondre à cela. Veuillez réessayer."

        # Synthesize voice response in the same language as the question
        audio_response = await tts.synthesize(response_text, language=detected_language)
        if audio_response:
            media_id = await upload_media(
                audio_bytes=audio_response,
                access_token=self._access_token,
                api_version=self._api_version,
                phone_number_id=self._phone_number_id,
                client=client
            )
            if media_id:
                await send_audio_message(
                    to_number=phone_number,
                    audio_id=media_id,
                    send_message_func=self._send_message
                )
                logger.info("voice_response_sent", phone=phone_number[-4:])
                # Record successful voice message processing
                voice_message_processed_total.labels(status="success").inc()
                return
            else:
                # Media upload failed
                voice_message_processed_total.labels(status="upload_failed").inc()
        else:
            # TTS synthesis failed
            voice_message_processed_total.labels(status="tts_failed").inc()
        
        # Fallback to text response
        await self.send_text_message(to_number=phone_number, text=response_text)
    
    async def send_text_message(
        self,
        to_number: str,
        text: str,
        preview_url: bool = False,
    ) -> Dict[str, Any]:
        """
        Send a text message via WhatsApp.
        
        Args:
            to_number: Recipient's phone number (E.164 format)
            text: Message text
            preview_url: Whether to show URL previews
            
        Returns:
            API response dict
        """
        async with self._message_semaphore:
            return await self._send_message(
                to_number=to_number,
                message_type="text",
                payload={
                    "text": {
                        "body": text,
                        "preview_url": preview_url,
                    }
                },
            )
    
    async def send_template_message(
        self,
        to_number: str,
        template_name: str,
        language_code: str = "en",
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Send a template message via WhatsApp.
        
        Args:
            to_number: Recipient's phone number
            template_name: Name of approved template
            language_code: Template language
            components: Template components (header, body, buttons)
            
        Returns:
            API response dict
        """
        payload = {
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            }
        }
        
        if components:
            payload["template"]["components"] = components
        
        async with self._message_semaphore:
            return await self._send_message(
                to_number=to_number,
                message_type="template",
                payload=payload,
            )
    
    async def send_image_message(
        self,
        to_number: str,
        image_url: Optional[str] = None,
        image_id: Optional[str] = None,
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send an image message via WhatsApp.
        
        Args:
            to_number: Recipient's phone number
            image_url: Public URL of image
            image_id: Media ID (if already uploaded)
            caption: Optional caption
            
        Returns:
            API response dict
        """
        image_payload = {}
        
        if image_id:
            image_payload["id"] = image_id
        elif image_url:
            image_payload["link"] = image_url
        else:
            raise WhatsAppException("Either image_url or image_id must be provided")
        
        if caption:
            image_payload["caption"] = caption
        
        async with self._message_semaphore:
            return await self._send_message(
                to_number=to_number,
                message_type="image",
                payload={"image": image_payload},
            )
    
    async def send_location_message(
        self,
        to_number: str,
        latitude: float,
        longitude: float,
        name: Optional[str] = None,
        address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a location message via WhatsApp.
        
        Args:
            to_number: Recipient's phone number
            latitude: Location latitude
            longitude: Location longitude
            name: Location name
            address: Location address
            
        Returns:
            API response dict
        """
        location_payload = {
            "latitude": latitude,
            "longitude": longitude,
        }
        
        if name:
            location_payload["name"] = name
        if address:
            location_payload["address"] = address
        
        async with self._message_semaphore:
            return await self._send_message(
                to_number=to_number,
                message_type="location",
                payload={"location": location_payload},
            )
    
    async def send_interactive_message(
        self,
        to_number: str,
        interactive_type: str,
        body_text: str,
        buttons: Optional[List[Dict[str, Any]]] = None,
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send an interactive message with buttons.
        
        Args:
            to_number: Recipient's phone number
            interactive_type: "button" or "list"
            body_text: Message body
            buttons: List of button configurations
            header_text: Optional header text
            footer_text: Optional footer text
            
        Returns:
            API response dict
        """
        interactive_payload = {
            "type": interactive_type,
            "body": {"text": body_text},
        }
        
        if interactive_type == "button" and buttons:
            interactive_payload["action"] = {"buttons": buttons}
        
        if header_text:
            interactive_payload["header"] = {
                "type": "text",
                "text": header_text,
            }
        
        if footer_text:
            interactive_payload["footer"] = {"text": footer_text}
        
        async with self._message_semaphore:
            return await self._send_message(
                to_number=to_number,
                message_type="interactive",
                payload={"interactive": interactive_payload},
            )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(WhatsAppRateLimitException),
        before_sleep=before_sleep_log(logger, "WARNING"),
    )
    async def _send_message(
        self,
        to_number: str,
        message_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Internal method to send WhatsApp message with retry logic.
        
        Args:
            to_number: Recipient's phone number
            message_type: Type of message
            payload: Message-specific payload
            
        Returns:
            API response dict
        """
        url = f"{self.BASE_URL}/{self._api_version}/{self._phone_number_id}/messages"
        
        request_body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": message_type,
            **payload,
        }
        
        try:
            client = await self._get_client()
            
            logger.debug(
                "whatsapp_send_message_started",
                to=to_number[-4:],
                type=message_type,
            )
            
            response = await client.post(url, json=request_body)
            
            if response.status_code == 200:
                data = response.json()
                
                logger.debug(
                    "whatsapp_send_message_success",
                    to=to_number[-4:],
                    message_id=data.get("messages", [{}])[0].get("id"),
                )
                
                return data
                
            elif response.status_code == 429:
                logger.warning("whatsapp_rate_limited", to=to_number[-4:])
                raise WhatsAppRateLimitException()
                
            else:
                error_data = response.json() if response.text else {}
                error_info = error_data.get("error", {})
                
                error_code = error_info.get("code")
                error_message = error_info.get("message", f"HTTP {response.status_code}")
                
                logger.error(
                    "whatsapp_send_message_failed",
                    to=to_number[-4:],
                    code=error_code,
                    error=error_message,
                )
                
                if error_code == 131047:
                    raise WhatsAppInvalidPhoneException(to_number)
                
                raise WhatsAppException(error_message, code=error_code)
                
        except httpx.TimeoutException as e:
            logger.error("whatsapp_timeout", to=to_number[-4:])
            raise WhatsAppException("Request timeout", original_error=e) from e
            
        except httpx.ConnectError as e:
            logger.error("whatsapp_connection_error", error=str(e))
            raise WhatsAppException("Connection failed", original_error=e) from e
            
        except (WhatsAppRateLimitException, WhatsAppInvalidPhoneException):
            raise
            
        except Exception as e:
            logger.error("whatsapp_unexpected_error", error=str(e))
            raise WhatsAppException(f"Unexpected error: {str(e)}", original_error=e) from e
    
    def _truncate_for_whatsapp(self, text: str) -> str:
        """
        Truncate text for WhatsApp while preserving the slogan.
        
        Args:
            text: Text to truncate
            
        Returns:
            Truncated text
        """
        slogan = "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        
        if len(text) <= self.MAX_MESSAGE_LENGTH:
            return text
        
        max_len = self.MAX_MESSAGE_LENGTH - len(slogan) - 5
        
        truncated = text[:max_len]
        
        # Try to cut at last sentence
        for punct in ['.', '!', '?']:
            last_punct = truncated.rfind(punct)
            if last_punct > max_len * 0.7:
                truncated = truncated[:last_punct + 1]
                break
        
        return truncated + "\n\n" + slogan
    
    async def mark_message_read(self, message_id: str) -> bool:
        """
        Mark a message as read (optional, shows read receipt).
        
        Args:
            message_id: WhatsApp message ID
            
        Returns:
            True if successful
        """
        url = f"{self.BASE_URL}/{self._api_version}/{self._phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        
        try:
            client = await self._get_client()
            response = await client.post(url, json=payload)
            return response.status_code == 200
        except Exception as e:
            logger.debug("mark_read_failed", error=str(e))
            return False
    
    async def get_media_url(self, media_id: str) -> Optional[str]:
        """
        Get download URL for media.
        
        Args:
            media_id: WhatsApp media ID
            
        Returns:
            Media URL or None
        """
        url = f"{self.BASE_URL}/{self._api_version}/{media_id}"
        
        try:
            client = await self._get_client()
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                return data.get("url")
            
            return None
            
        except Exception as e:
            logger.error("get_media_url_failed", error=str(e), media_id=media_id)
            return None
    
    async def get_opt_out_list(self) -> List[str]:
        """
        Get list of opted-out phone numbers.
        
        Returns:
            List of phone numbers
        """
        opt_outs = await cache_service.get_opt_out_list()
        return list(opt_outs)
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check WhatsApp service health.
        
        Returns:
            Health status dict
        """
        try:
            # Test API connectivity by getting business profile
            url = f"{self.BASE_URL}/{self._api_version}/{self._phone_number_id}/whatsapp_business_profile"
            
            client = await self._get_client()
            response = await client.get(
                url,
                params={"fields": "about,address,description,email,profile_picture_url,websites,vertical"},
            )
            
            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "service": "whatsapp",
                    "phone_number_id": self._phone_number_id,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            else:
                return {
                    "status": "degraded",
                    "service": "whatsapp",
                    "error": f"HTTP {response.status_code}",
                    "timestamp": datetime.utcnow().isoformat(),
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "whatsapp",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    async def get_business_profile(self) -> Dict[str, Any]:
        """
        Get WhatsApp Business Profile information.
        
        Returns:
            Business profile dict
        """
        url = f"{self.BASE_URL}/{self._api_version}/{self._phone_number_id}/whatsapp_business_profile"
        
        try:
            client = await self._get_client()
            response = await client.get(
                url,
                params={"fields": "about,address,description,email,profile_picture_url,websites,vertical"},
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "success",
                    "data": data.get("data", [{}])[0] if data.get("data") else {},
                }
            else:
                return {
                    "status": "error",
                    "error": f"HTTP {response.status_code}",
                }
                
        except Exception as e:
            logger.error("get_business_profile_failed", error=str(e))
            return {"status": "error", "error": str(e)}