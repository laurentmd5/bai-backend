"""
Request models package for Company Bot.
Contains Pydantic schemas for validating incoming requests.
"""

from app.models.request.chat import (
    ChatMessageRequest,
    ChatFeedbackRequest,
)

from app.models.request.admin import (
    AdminLoginRequest,
    AdminLogin2FARequest,
    AdminRefreshTokenRequest,
    AdminChangePasswordRequest,
    AdminResetPasswordRequest,
    AdminEnable2FARequest,
    AdminVerify2FARequest,
    AdminDisable2FARequest,
)

from app.models.request.whatsapp import (
    WhatsAppWebhookRequest,
    WhatsAppMessage,
    WhatsAppContact,
    WhatsAppMetadata,
    WhatsAppValue,
    WhatsAppChange,
    WhatsAppEntry,
)

from app.models.request.knowledge import (
    KnowledgeDocumentUploadRequest,
    KnowledgeDocumentUpdateRequest,
)

from app.models.request.broadcast import (
    BroadcastRequest,
    BroadcastTemplateParameter,
)

from app.models.request.common import (
    PaginationParams,
    DateRangeParams,
    SortParams,
    FilterParams,
)

__all__ = [
    "ChatMessageRequest",
    "ChatFeedbackRequest",
    "AdminLoginRequest",
    "AdminLogin2FARequest",
    "AdminRefreshTokenRequest",
    "AdminChangePasswordRequest",
    "AdminResetPasswordRequest",
    "AdminEnable2FARequest",
    "AdminVerify2FARequest",
    "AdminDisable2FARequest",
    "WhatsAppWebhookRequest",
    "WhatsAppMessage",
    "WhatsAppContact",
    "WhatsAppMetadata",
    "WhatsAppValue",
    "WhatsAppChange",
    "WhatsAppEntry",
    "KnowledgeDocumentUploadRequest",
    "KnowledgeDocumentUpdateRequest",
    "BroadcastRequest",
    "BroadcastTemplateParameter",
    "PaginationParams",
    "DateRangeParams",
    "SortParams",
    "FilterParams",
]
