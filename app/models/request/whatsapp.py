"""
WhatsApp webhook request models for Company Bot.
Models the Meta WhatsApp Cloud API webhook payload structure.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class WhatsAppProfile(BaseModel):
    """Sender profile information."""
    
    name: Optional[str] = Field(None, description="Sender's display name")


class WhatsAppContact(BaseModel):
    """Contact information for the sender."""
    
    profile: Optional[WhatsAppProfile] = Field(None, description="Profile information")
    wa_id: Optional[str] = Field(None, description="WhatsApp ID")
    
    # NEW: Meta sends this in recent API versions
    user_id: Optional[str] = Field(None, description="Meta user ID")
    
    model_config = {"extra": "ignore"}


class WhatsAppText(BaseModel):
    """Text message content."""
    
    body: str = Field(..., description="Message text content")


class WhatsAppButton(BaseModel):
    """Button interaction."""
    
    payload: Optional[str] = Field(None, description="Button payload")
    text: Optional[str] = Field(None, description="Button text")


class WhatsAppInteractive(BaseModel):
    """Interactive message (list, button)."""
    
    type: Optional[str] = Field(None, description="Interactive type")
    button_reply: Optional[WhatsAppButton] = Field(None, description="Button reply")
    list_reply: Optional[Dict[str, Any]] = Field(None, description="List reply")


class WhatsAppLocation(BaseModel):
    """Location message."""
    
    latitude: float = Field(..., description="Latitude")
    longitude: float = Field(..., description="Longitude")
    name: Optional[str] = Field(None, description="Location name")
    address: Optional[str] = Field(None, description="Address")


class WhatsAppImage(BaseModel):
    """Image media."""
    
    mime_type: Optional[str] = Field(None, description="MIME type")
    sha256: Optional[str] = Field(None, description="SHA256 hash")
    id: Optional[str] = Field(None, description="Media ID")
    caption: Optional[str] = Field(None, description="Caption")


class WhatsAppDocument(BaseModel):
    """Document media."""
    
    filename: Optional[str] = Field(None, description="Filename")
    mime_type: Optional[str] = Field(None, description="MIME type")
    sha256: Optional[str] = Field(None, description="SHA256 hash")
    id: Optional[str] = Field(None, description="Media ID")
    caption: Optional[str] = Field(None, description="Caption")


class WhatsAppAudio(BaseModel):
    """Audio media."""
    
    mime_type: Optional[str] = Field(None, description="MIME type")
    sha256: Optional[str] = Field(None, description="SHA256 hash")
    id: Optional[str] = Field(None, description="Media ID")
    voice: Optional[bool] = Field(None, description="Is voice note")


class WhatsAppVideo(BaseModel):
    """Video media."""
    
    mime_type: Optional[str] = Field(None, description="MIME type")
    sha256: Optional[str] = Field(None, description="SHA256 hash")
    id: Optional[str] = Field(None, description="Media ID")
    caption: Optional[str] = Field(None, description="Caption")


class WhatsAppSticker(BaseModel):
    """Sticker media."""
    
    mime_type: Optional[str] = Field(None, description="MIME type")
    sha256: Optional[str] = Field(None, description="SHA256 hash")
    id: Optional[str] = Field(None, description="Media ID")
    animated: Optional[bool] = Field(None, description="Is animated")


class WhatsAppReaction(BaseModel):
    """Reaction to a message."""
    
    message_id: str = Field(..., description="ID of message being reacted to")
    emoji: str = Field(..., description="Emoji reaction")


class WhatsAppOrder(BaseModel):
    """Order message."""
    
    catalog_id: Optional[str] = Field(None, description="Catalog ID")
    product_items: Optional[List[Dict[str, Any]]] = Field(None, description="Product items")
    text: Optional[str] = Field(None, description="Order text")


class WhatsAppReferral(BaseModel):
    """Referral information."""
    
    source_url: Optional[str] = Field(None, description="Source URL")
    source_type: Optional[str] = Field(None, description="Source type")
    source_id: Optional[str] = Field(None, description="Source ID")
    headline: Optional[str] = Field(None, description="Headline")
    body: Optional[str] = Field(None, description="Body")


class WhatsAppContext(BaseModel):
    """Context for replied messages."""
    
    from_: Optional[str] = Field(None, alias="from", description="Sender of original message")
    id: Optional[str] = Field(None, description="ID of original message")


class WhatsAppIdentity(BaseModel):
    """Identity information."""
    
    acknowledged: Optional[str] = Field(None, description="Acknowledgment state")
    created_timestamp: Optional[str] = Field(None, description="Creation timestamp")
    hash: Optional[str] = Field(None, description="Identity hash")


class WhatsAppError(BaseModel):
    """Error information."""
    
    code: Optional[int] = Field(None, description="Error code")
    title: Optional[str] = Field(None, description="Error title")
    message: Optional[str] = Field(None, description="Error message")
    error_data: Optional[Dict[str, Any]] = Field(None, description="Additional error data")


class WhatsAppMessage(BaseModel):
    """
    WhatsApp message object from webhook.

    NOTE: 'to' is OPTIONAL — Meta does not include it in inbound webhooks.
    It only appears in messages you send (outbound). Making it required
    caused a Pydantic validation error on every real Meta webhook.
    """
    
    id: str = Field(..., description="Unique message ID")
    from_: str = Field(..., alias="from", description="Sender's phone number")
    
    # FIX: Optional — Meta omits this field in inbound webhooks
    to: Optional[str] = Field(None, description="Recipient's phone number (not sent by Meta inbound)")
    
    timestamp: str = Field(..., description="Unix timestamp")
    
    type: str = Field(
        ...,
        description="Message type",
        examples=["text", "image", "video", "audio", "document",
                  "sticker", "location", "contacts", "interactive",
                  "button", "reaction", "order", "system"]
    )
    
    # NEW: Meta sends this in recent API versions (user identifier)
    from_user_id: Optional[str] = Field(None, description="Meta user ID (recent API versions)")
    
    text: Optional[WhatsAppText] = Field(None, description="Text message content")
    image: Optional[WhatsAppImage] = Field(None, description="Image media")
    video: Optional[WhatsAppVideo] = Field(None, description="Video media")
    audio: Optional[WhatsAppAudio] = Field(None, description="Audio media")
    document: Optional[WhatsAppDocument] = Field(None, description="Document media")
    sticker: Optional[WhatsAppSticker] = Field(None, description="Sticker media")
    location: Optional[WhatsAppLocation] = Field(None, description="Location")
    interactive: Optional[WhatsAppInteractive] = Field(None, description="Interactive message")
    button: Optional[WhatsAppButton] = Field(None, description="Button")
    reaction: Optional[WhatsAppReaction] = Field(None, description="Reaction")
    order: Optional[WhatsAppOrder] = Field(None, description="Order")
    contacts: Optional[List[WhatsAppContact]] = Field(None, description="Contacts")
    context: Optional[WhatsAppContext] = Field(None, description="Reply context")
    referral: Optional[WhatsAppReferral] = Field(None, description="Referral")
    identity: Optional[WhatsAppIdentity] = Field(None, description="Identity")
    errors: Optional[List[WhatsAppError]] = Field(None, description="Errors")
    
    # Pydantic config: accept both 'from' (alias) and extra fields from Meta
    model_config = {"populate_by_name": True, "extra": "ignore"}
    
    @property
    def phone_number(self) -> str:
        """Get sender's phone number."""
        return self.from_
    
    @property
    def message_id(self) -> str:
        """Get message ID."""
        return self.id
    
    @property
    def text_content(self) -> Optional[str]:
        """Get text content if message is text type."""
        if self.text:
            return self.text.body
        return None
    
    @property
    def is_text(self) -> bool:
        """Check if message is text type."""
        return self.type == "text"
    
    @property
    def is_media(self) -> bool:
        """Check if message contains media."""
        return self.type in ("image", "video", "audio", "document", "sticker")
    
    @property
    def is_interactive(self) -> bool:
        """Check if message is interactive."""
        return self.type in ("interactive", "button")


class WhatsAppMetadata(BaseModel):
    """Metadata for the webhook payload."""
    
    display_phone_number: Optional[str] = Field(None, description="Business phone number")
    phone_number_id: Optional[str] = Field(None, description="Phone number ID")


class WhatsAppStatus(BaseModel):
    """Status information for a message."""
    
    id: str = Field(..., description="Message ID")
    status: str = Field(..., description="Status", examples=["sent", "delivered", "read", "failed"])
    timestamp: str = Field(..., description="Unix timestamp")
    recipient_id: str = Field(..., description="Recipient ID")
    conversation: Optional[Dict[str, Any]] = Field(None, description="Conversation info")
    pricing: Optional[Dict[str, Any]] = Field(None, description="Pricing info")
    errors: Optional[List[WhatsAppError]] = Field(None, description="Errors")


class WhatsAppValue(BaseModel):
    """Value object containing messages, statuses, or contacts."""
    
    messaging_product: str = Field(default="whatsapp", description="Product identifier")
    metadata: Optional[WhatsAppMetadata] = Field(None, description="Metadata")
    contacts: Optional[List[WhatsAppContact]] = Field(None, description="Contacts")
    messages: Optional[List[WhatsAppMessage]] = Field(None, description="Messages")
    statuses: Optional[List[WhatsAppStatus]] = Field(None, description="Status updates")


class WhatsAppChange(BaseModel):
    """Change object in the webhook payload."""
    
    value: WhatsAppValue = Field(..., description="Value object")
    field: str = Field(default="messages", description="Field type")


class WhatsAppEntry(BaseModel):
    """Entry object containing changes."""
    
    id: str = Field(..., description="WhatsApp Business Account ID")
    changes: List[WhatsAppChange] = Field(..., description="Changes")


class WhatsAppWebhookRequest(BaseModel):
    """
    Complete WhatsApp webhook request payload.
    """
    
    object: str = Field(default="whatsapp_business_account", description="Object type")
    entry: List[WhatsAppEntry] = Field(..., description="Entry array")
    
    def get_messages(self) -> List[WhatsAppMessage]:
        """Extract all messages from the webhook payload."""
        messages = []
        for entry in self.entry:
            for change in entry.changes:
                if change.value.messages:
                    messages.extend(change.value.messages)
        return messages
    
    def get_first_message(self) -> Optional[WhatsAppMessage]:
        """Get the first message from the webhook payload."""
        messages = self.get_messages()
        return messages[0] if messages else None
    
    def has_messages(self) -> bool:
        """Check if payload contains any messages."""
        return len(self.get_messages()) > 0
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "object": "whatsapp_business_account",
                "entry": [{
                    "id": "123456789",
                    "changes": [{
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "+2202121289",
                                "phone_number_id": "123456789"
                            },
                            "contacts": [{
                                "profile": {"name": "John Doe"},
                                "wa_id": "2201234567"
                            }],
                            "messages": [{
                                "id": "wamid.xxx",
                                "from": "2201234567",
                                "to": "2202121289",
                                "timestamp": "1713340200",
                                "type": "text",
                                "text": {"body": "Hello Barrow AI"}
                            }]
                        },
                        "field": "messages"
                    }]
                }]
            }
        }
    }
