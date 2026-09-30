"""
Response models package for Company Bot.
Contains Pydantic schemas for serializing API responses.
"""

from app.models.response.chat import (
    ChatMessageResponse,
    ChatSourceResponse,
    ChatHistoryResponse,
    ChatFeedbackResponse,
    ChatFallbackResponse,
)

from app.models.response.common import (
    ErrorResponse,
    HealthResponse,
    ServiceHealthResponse,
    PaginatedResponse,
    MetricsResponse,
    CacheStatsResponse,
)

from app.models.response.admin import (
    TokenResponse,
    TwoFactorSetupResponse,
    AdminUserResponse,
    AdminSessionResponse,
    AdminLoginResponse,
    QRCodeResponse,
    BackupCodesResponse,
)

from app.models.response.analytics import (
    AnalyticsOverviewResponse,
    AnalyticsQuestionsResponse,
    AnalyticsSentimentResponse,
    AnalyticsLatencyResponse,
    AnalyticsDailyStatsResponse,
    AnalyticsTopQuestion,
    AnalyticsSentimentTrend,
    AnalyticsLatencyDistribution,
)

from app.models.response.conversation import (
    ConversationResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationExportResponse,
)

from app.models.response.knowledge import (
    KnowledgeDocumentResponse,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentUploadResponse,
    KnowledgeDocumentIndexStatusResponse,
)

from app.models.response.audit import (
    AuditLogResponse,
    AuditLogListResponse,
)

from app.models.response.whatsapp import (
    WhatsAppOptOutResponse,
    WhatsAppOptOutListResponse,
    WhatsAppWebhookVerificationResponse,
    WhatsAppSendMessageResponse,
)

__all__ = [
    # Chat responses
    "ChatMessageResponse",
    "ChatSourceResponse",
    "ChatHistoryResponse",
    "ChatFeedbackResponse",
    "ChatFallbackResponse",
    
    # Common responses
    "ErrorResponse",
    "HealthResponse",
    "ServiceHealthResponse",
    "PaginatedResponse",
    "MetricsResponse",
    "CacheStatsResponse",
    
    # Admin responses
    "TokenResponse",
    "TwoFactorSetupResponse",
    "AdminUserResponse",
    "AdminSessionResponse",
    "AdminLoginResponse",
    "QRCodeResponse",
    "BackupCodesResponse",
    
    # Analytics responses
    "AnalyticsOverviewResponse",
    "AnalyticsQuestionsResponse",
    "AnalyticsSentimentResponse",
    "AnalyticsLatencyResponse",
    "AnalyticsDailyStatsResponse",
    "AnalyticsTopQuestion",
    "AnalyticsSentimentTrend",
    "AnalyticsLatencyDistribution",
    
    # Conversation responses
    "ConversationResponse",
    "ConversationDetailResponse",
    "ConversationListResponse",
    "ConversationExportResponse",
    
    # Knowledge responses
    "KnowledgeDocumentResponse",
    "KnowledgeDocumentListResponse",
    "KnowledgeDocumentUploadResponse",
    "KnowledgeDocumentIndexStatusResponse",
    
    # Audit responses
    "AuditLogResponse",
    "AuditLogListResponse",
    
    # WhatsApp responses
    "WhatsAppOptOutResponse",
    "WhatsAppOptOutListResponse",
    "WhatsAppWebhookVerificationResponse",
    "WhatsAppSendMessageResponse",
]
