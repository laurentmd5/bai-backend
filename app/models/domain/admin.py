"""
Admin user domain models for BARROW.AI.
Manages administrative users, roles, authentication, and audit logging.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from uuid import uuid4
from enum import Enum

from sqlalchemy import (
    String,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
    Index,
    CheckConstraint,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.domain.knowledge import KnowledgeDocument
    from app.models.domain.session import Session


class AdminRole(str, Enum):
    """Admin user roles for RBAC."""
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    VIEWER = "viewer"
    AUDITOR = "auditor"


class AuditAction(str, Enum):
    """Types of auditable actions."""
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    TWO_FACTOR_ENABLED = "2FA_ENABLED"
    TWO_FACTOR_DISABLED = "2FA_DISABLED"
    TWO_FACTOR_VERIFIED = "2FA_VERIFIED"
    TWO_FACTOR_FAILED = "2FA_FAILED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    EXPORT_DATA = "EXPORT_DATA"
    VIEW_CONVERSATIONS = "VIEW_CONVERSATIONS"
    VIEW_AUDIT_LOGS = "VIEW_AUDIT_LOGS"
    KNOWLEDGE_UPLOAD = "KNOWLEDGE_UPLOAD"
    KNOWLEDGE_DELETE = "KNOWLEDGE_DELETE"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    USER_DELETED = "USER_DELETED"
    BACKUP_CODE_USED = "BACKUP_CODE_USED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    ACCOUNT_UNLOCKED = "ACCOUNT_UNLOCKED"


class AdminUser(Base):
    """
    Admin user model for dashboard authentication.
    Supports 2FA, backup codes, account locking, and role-based access control.
    """
    
    __tablename__ = "admin_users"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        comment="Unique admin user identifier"
    )
    
    # Basic information
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Admin email address (login identifier)"
    )
    
    full_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Admin full name"
    )
    
    # Authentication
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Argon2id password hash"
    )
    
    # Role and status
    role: Mapped[str] = mapped_column(
        String(20),
        default=AdminRole.VIEWER.value,
        nullable=False,
        comment="Admin role for RBAC"
    )
    
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Whether account is active"
    )
    
    # Two-factor authentication
    two_factor_secret: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="TOTP secret (encrypted at rest)"
    )
    
    two_factor_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether 2FA is enabled"
    )
    
    backup_codes: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Hashed backup codes for 2FA recovery"
    )
    
    # Security tracking
    failed_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of consecutive failed login attempts"
    )
    
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Account locked until this timestamp"
    )
    
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful login timestamp"
    )
    
    last_ip: Mapped[Optional[str]] = mapped_column(
        String(45),  # Supports both IPv4 and IPv6
        nullable=True,
        comment="IP address of last login"
    )
    
    # Password management
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When password was last changed"
    )
    
    password_reset_token: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Password reset token (hashed)"
    )
    
    password_reset_expires: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Password reset token expiration"
    )
    
    # Preferences
    preferences: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="User preferences (theme, notifications, etc.)"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        comment="When the account was created"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="When the account was last updated"
    )
    
    # Relationships
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="admin",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    
    knowledge_documents: Mapped[List["KnowledgeDocument"]] = relationship(
        "KnowledgeDocument",
        back_populates="uploaded_by_user",
        lazy="selectin"
    )
    
    # Table constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "role IN ('superadmin', 'admin', 'viewer', 'auditor')",
            name="ck_admin_users_role_valid"
        ),
        CheckConstraint(
            "failed_attempts >= 0",
            name="ck_admin_users_failed_attempts_non_negative"
        ),
        Index("idx_admin_users_email_active", "email", "is_active"),
        Index("idx_admin_users_role", "role"),
        Index("idx_admin_users_locked", "locked_until", postgresql_where="locked_until IS NOT NULL"),
    )
    
    def __repr__(self) -> str:
        return f"<AdminUser(id={self.id}, email={self.email}, role={self.role})>"
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """
        Convert admin user to dictionary.
        
        Args:
            include_sensitive: Whether to include sensitive fields
            
        Returns:
            Dict containing admin user data
        """
        result = {
            "id": str(self.id),
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
            "two_factor_enabled": self.two_factor_enabled,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_sensitive:
            result.update({
                "failed_attempts": self.failed_attempts,
                "locked_until": self.locked_until.isoformat() if self.locked_until else None,
                "password_changed_at": self.password_changed_at.isoformat() if self.password_changed_at else None,
                "preferences": self.preferences,
            })
        
        return result
    
    def is_locked(self) -> bool:
        """Check if account is currently locked."""
        if not self.locked_until:
            return False
        return self.locked_until > datetime.utcnow()
    
    def increment_failed_attempts(self) -> None:
        """Increment failed login attempts and lock if threshold reached."""
        from app.core.config import settings
        
        self.failed_attempts += 1
        
        if self.failed_attempts >= settings.ADMIN_MAX_FAILED_ATTEMPTS:
            from datetime import timedelta
            self.locked_until = datetime.utcnow() + timedelta(
                minutes=settings.ADMIN_LOCKOUT_MINUTES
            )
    
    def reset_failed_attempts(self) -> None:
        """Reset failed login attempts on successful login."""
        self.failed_attempts = 0
        self.locked_until = None
    
    def record_login(self, ip_address: Optional[str] = None) -> None:
        """Record successful login."""
        self.last_login = datetime.utcnow()
        self.last_ip = ip_address
        self.reset_failed_attempts()
    
    def has_permission(self, required_role: AdminRole) -> bool:
        """
        Check if user has sufficient role permissions.
        
        Role hierarchy: superadmin > admin > auditor > viewer
        """
        role_hierarchy = {
            AdminRole.SUPERADMIN.value: 4,
            AdminRole.ADMIN.value: 3,
            AdminRole.AUDITOR.value: 2,
            AdminRole.VIEWER.value: 1,
        }
        
        user_level = role_hierarchy.get(self.role, 0)
        required_level = role_hierarchy.get(required_role.value, 0)
        
        return user_level >= required_level


class AuditLog(Base):
    """
    Audit log model for tracking administrative actions.
    Immutable record of all security-relevant events.
    """
    
    __tablename__ = "audit_logs"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        comment="Unique audit log identifier"
    )
    
    # Foreign key to admin user
    admin_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Admin user who performed the action"
    )
    
    # Action information
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of action performed"
    )
    
    # Request context
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),  # Supports both IPv4 and IPv6
        nullable=True,
        comment="IP address of the request"
    )
    
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="User agent of the request"
    )
    
    # Action details
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional action-specific details"
    )
    
    # Outcome
    severity: Mapped[str] = mapped_column(
        String(10),
        default="INFO",
        nullable=False,
        comment="Severity level: INFO, WARN, CRITICAL"
    )
    
    success: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether the action was successful"
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if action failed"
    )
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="When the action occurred"
    )
    
    # Relationships
    admin: Mapped[Optional["AdminUser"]] = relationship(
        "AdminUser",
        back_populates="audit_logs",
        lazy="selectin"
    )
    
    # Table constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "severity IN ('INFO', 'WARN', 'CRITICAL')",
            name="ck_audit_logs_severity_valid"
        ),
        Index("idx_audit_logs_created_at", "created_at"),
        Index("idx_audit_logs_action_created", "action", "created_at"),
        Index("idx_audit_logs_severity", "severity", postgresql_where="severity IN ('WARN', 'CRITICAL')"),
        Index("idx_audit_logs_recent", "created_at", postgresql_where="created_at > NOW() - INTERVAL '7 days'"),
    )
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, admin={self.admin_id})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert audit log to dictionary."""
        return {
            "id": str(self.id),
            "admin_id": str(self.admin_id) if self.admin_id else None,
            "admin_email": self.admin.email if self.admin else None,
            "action": self.action,
            "ip_address": str(self.ip_address) if self.ip_address else None,
            "user_agent": self.user_agent,
            "details": self.details,
            "severity": self.severity,
            "success": self.success,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }