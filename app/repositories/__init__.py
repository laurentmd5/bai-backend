"""
Repositories package for Company Bot.
Exports all repository classes for dependency injection.
"""

from app.repositories.base import BaseRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.admin_repository import AdminRepository, AuditLogRepository
from app.repositories.knowledge_repository import KnowledgeRepository

__all__ = [
    "BaseRepository",
    "ConversationRepository",
    "SessionRepository",
    "AdminRepository",
    "AuditLogRepository",
    "KnowledgeRepository",
]
