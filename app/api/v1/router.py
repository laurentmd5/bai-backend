"""
API v1 router for Company Bot.
Aggregates all endpoint routers.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    chat,
    whatsapp,
    health,
    internal,
)
from app.api.v1.endpoints.admin import (
    auth as admin_auth,
    two_factor as admin_2fa,
    analytics as admin_analytics,
    conversations as admin_conversations,
    knowledge as admin_knowledge,
    users as admin_users,
    audit as admin_audit,
    health as admin_health,
)

# Main API router
api_router = APIRouter()

# Public endpoints
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(whatsapp.router, prefix="/whatsapp", tags=["WhatsApp"])
api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(internal.router, prefix="/internal", tags=["Internal"])


# Admin endpoints
api_router.include_router(admin_auth.router, prefix="/admin", tags=["Admin Authentication"])
api_router.include_router(admin_2fa.router, prefix="/admin", tags=["Admin 2FA"])
api_router.include_router(admin_health.router, prefix="/admin", tags=["Admin Health"])
api_router.include_router(admin_analytics.router, prefix="/admin", tags=["Admin Analytics"])
api_router.include_router(admin_conversations.router, prefix="/admin", tags=["Admin Conversations"])
api_router.include_router(admin_knowledge.router, prefix="/admin", tags=["Admin Knowledge"])
api_router.include_router(admin_users.router, prefix="/admin", tags=["Admin Users"])
api_router.include_router(admin_audit.router, prefix="/admin", tags=["Admin Audit"])
