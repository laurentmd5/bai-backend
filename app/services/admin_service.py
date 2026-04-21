"""
Admin Service for BARROW.AI.
Handles admin authentication, 2FA, user management, and audit logging.
"""

import asyncio
import secrets
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import (
    AuthenticationException,
    AuthorizationException,
    ValidationException,
    NotFoundException,
    AccountLockedException,
    TwoFactorRequiredException,
    ErrorCode,
)
from app.core.security import (
    hash_password,
    verify_password,
    create_jwt_token,
    create_token_pair,
    decode_jwt_token,
    refresh_access_token as refresh_jwt_token,
    generate_totp_secret,
    generate_totp_uri,
    verify_totp,
    generate_backup_codes,
    hash_backup_code,
    verify_backup_code,
    generate_csrf_token,
    encrypt_field,
    decrypt_field,
    generate_secure_token,
    validate_email,
    validate_password_strength,
)
from app.services.cache.redis_cache import cache_service, CacheNamespace
from app.services.validation.security_validator import SecurityValidator
from app.repositories.admin_repository import AdminRepository, AuditLogRepository
from app.models.domain.admin import AdminRole, AuditAction

logger = get_logger(__name__)


class AdminService:
    """
    Admin service for BARROW.AI dashboard.
    
    Handles:
    - Admin authentication (login, logout, refresh)
    - Two-factor authentication (setup, verify, disable)
    - Password management (change, reset)
    - User management (create, update, deactivate)
    - Role-based access control (RBAC)
    - Audit logging
    - Session management
    """
    
    # Permission matrix for role-based access control
    ROLE_PERMISSIONS = {
        AdminRole.SUPERADMIN.value: [
            "admin:read", "admin:write", "admin:delete",
            "users:read", "users:write", "users:delete",
            "conversations:read", "conversations:export",
            "analytics:read", "analytics:export",
            "knowledge:read", "knowledge:write", "knowledge:delete",
            "audit:read", "audit:export",
            "settings:read", "settings:write",
            "broadcast:send", "broadcast:schedule",
        ],
        AdminRole.ADMIN.value: [
            "admin:read",
            "users:read",
            "conversations:read", "conversations:export",
            "analytics:read", "analytics:export",
            "knowledge:read", "knowledge:write",
            "audit:read",
            "broadcast:send",
        ],
        AdminRole.AUDITOR.value: [
            "admin:read",
            "conversations:read", "conversations:export",
            "analytics:read", "analytics:export",
            "audit:read", "audit:export",
        ],
        AdminRole.VIEWER.value: [
            "conversations:read",
            "analytics:read",
        ],
    }
    
    def __init__(
        self,
        admin_repository: AdminRepository,
        audit_log_repository: AuditLogRepository,
    ):
        """
        Initialize admin service.
        
        Args:
            admin_repository: Repository for admin users
            audit_log_repository: Repository for audit logs
        """
        self._admin_repo = admin_repository
        self._audit_repo = audit_log_repository
        self._security_validator = SecurityValidator()
    
    # =========================================================================
    # AUTHENTICATION
    # =========================================================================
    
    async def login(
        self,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Authenticate an admin user (first step).
        
        Args:
            email: Admin email
            password: Admin password
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            Login response with tokens or 2FA requirement
            
        Raises:
            AuthenticationException: If credentials are invalid
            AccountLockedException: If account is locked
        """
        # Validate email format
        if not validate_email(email):
            raise AuthenticationException(
                "Invalid email format",
                code=ErrorCode.INVALID_CREDENTIALS
            )
        
        # Get user
        admin = await self._admin_repo.get_by_email(email)
        
        if not admin:
            # Log failed attempt
            await self._audit_repo.create_log(
                action=AuditAction.LOGIN_FAILED,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"email": email, "reason": "user_not_found"},
                severity="WARN",
                success=False,
            )
            raise AuthenticationException(
                "Invalid credentials",
                code=ErrorCode.INVALID_CREDENTIALS
            )
        
        # Check if account is active
        if not admin.is_active:
            await self._audit_repo.create_log(
                action=AuditAction.LOGIN_FAILED,
                admin_id=admin.id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "account_inactive"},
                severity="WARN",
                success=False,
            )
            raise AuthenticationException(
                "Account is deactivated",
                code=ErrorCode.ACCOUNT_LOCKED
            )
        
        # Check if account is locked
        if admin.is_locked():
            await self._audit_repo.create_log(
                action=AuditAction.LOGIN_FAILED,
                admin_id=admin.id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "account_locked"},
                severity="WARN",
                success=False,
            )
            raise AccountLockedException(admin.locked_until.isoformat())
        
        # Verify password
        if not verify_password(admin.password_hash, password):
            # Record failed attempt
            failures = await self._admin_repo.record_login_failure(admin.id)
            
            await self._audit_repo.create_log(
                action=AuditAction.LOGIN_FAILED,
                admin_id=admin.id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "invalid_password", "failures": failures},
                severity="WARN" if failures < 3 else "CRITICAL",
                success=False,
            )
            
            raise AuthenticationException(
                "Invalid credentials",
                code=ErrorCode.INVALID_CREDENTIALS
            )
        
        # Check if 2FA is enabled
        if admin.two_factor_enabled:
            # Create 2FA session token
            session_token = generate_secure_token(32)
            
            await cache_service.set(
                CacheNamespace.TWO_FACTOR_SESSION,
                session_token,
                {
                    "admin_id": str(admin.id),
                    "email": admin.email,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                },
                ttl=300,  # 5 minutes
            )
            
            await self._audit_repo.create_log(
                action=AuditAction.LOGIN_SUCCESS,
                admin_id=admin.id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"step": "first_factor", "requires_2fa": True},
                severity="INFO",
                success=True,
            )
            
            return {
                "requires_2fa": True,
                "session_token": session_token,
                "expires_in": 300,
                "user": None,
                "tokens": None,
            }
        
        # No 2FA - complete login
        return await self._complete_login(admin, ip_address, user_agent)
    
    async def verify_2fa(
        self,
        session_token: str,
        two_factor_code: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verify 2FA code and complete login.
        
        Args:
            session_token: Session token from initial login
            two_factor_code: TOTP code or backup code
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            Tokens response
            
        Raises:
            AuthenticationException: If code is invalid or session expired
        """
        # Get session data
        session_data = await cache_service.get(
            CacheNamespace.TWO_FACTOR_SESSION,
            session_token,
        )
        
        if not session_data:
            await self._audit_repo.create_log(
                action=AuditAction.TWO_FACTOR_FAILED,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "session_expired"},
                severity="WARN",
                success=False,
            )
            raise AuthenticationException(
                "2FA session expired. Please login again.",
                code=ErrorCode.SESSION_EXPIRED
            )
        
        admin_id = UUID(session_data["admin_id"])
        admin = await self._admin_repo.get_by_id(admin_id)
        
        if not admin:
            raise AuthenticationException("User not found")
        
        # Get decrypted 2FA secret
        two_factor_secret = decrypt_field(admin.two_factor_secret)
        
        # Verify TOTP code
        is_valid_totp = verify_totp(two_factor_secret, two_factor_code)
        
        is_valid_backup = False
        used_backup_hash = None
        
        if not is_valid_totp and admin.backup_codes:
            # Try backup codes
            is_valid_backup, used_backup_hash = verify_backup_code(
                admin.backup_codes,
                two_factor_code,
            )
        
        if not is_valid_totp and not is_valid_backup:
            await self._audit_repo.create_log(
                action=AuditAction.TWO_FACTOR_FAILED,
                admin_id=admin.id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "invalid_code"},
                severity="WARN",
                success=False,
            )
            raise AuthenticationException(
                "Invalid 2FA code",
                code=ErrorCode.INVALID_2FA_CODE
            )
        
        # If backup code used, remove it
        if is_valid_backup and used_backup_hash:
            await self._admin_repo.use_backup_code(admin.id, used_backup_hash)
            await self._audit_repo.create_log(
                action=AuditAction.BACKUP_CODE_USED,
                admin_id=admin.id,
                ip_address=ip_address,
                user_agent=user_agent,
                severity="INFO",
                success=True,
            )
        
        # Delete 2FA session
        await cache_service.delete(CacheNamespace.TWO_FACTOR_SESSION, session_token)
        
        # Complete login
        return await self._complete_login(admin, ip_address, user_agent)
    
    async def _complete_login(
        self,
        admin: Any,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Complete login process and generate tokens.
        
        Args:
            admin: AdminUser instance
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            Tokens response
        """
        # Record successful login
        await self._admin_repo.record_login_success(admin.id, ip_address)
        
        # Create JWT tokens
        user_data = {
            "sub": str(admin.id),
            "email": admin.email,
            "role": admin.role,
            "full_name": admin.full_name,
        }
        
        tokens = create_token_pair(user_data)
        
        # Create admin session in Redis
        session_id = generate_secure_token(16)
        csrf_token = generate_csrf_token(session_id)
        
        await cache_service.hset(
            CacheNamespace.ADMIN_SESSION,
            session_id,
            mapping={
                "admin_id": str(admin.id),
                "email": admin.email,
                "role": admin.role,
                "csrf_token": csrf_token,
                "ip_address": ip_address or "",
                "user_agent": user_agent or "",
                "created_at": datetime.utcnow().isoformat(),
            },
            ttl=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        
        await self._audit_repo.create_log(
            action=AuditAction.LOGIN_SUCCESS,
            admin_id=admin.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"session_id": session_id},
            severity="INFO",
            success=True,
        )
        
        logger.info("admin_logged_in", email=admin.email, admin_id=str(admin.id))
        
        return {
            "requires_2fa": False,
            "session_token": None,
            "user": {
                "id": str(admin.id),
                "email": admin.email,
                "full_name": admin.full_name,
                "role": admin.role,
                "is_active": admin.is_active,
                "two_factor_enabled": admin.two_factor_enabled,
                "permissions": self.ROLE_PERMISSIONS.get(admin.role, []),
            },
            "tokens": {
                **tokens,
                "csrf_token": csrf_token,
            },
        }
    
    async def logout(
        self,
        admin_id: UUID,
        session_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Logout admin user.
        
        Args:
            admin_id: Admin user ID
            session_id: Session ID to invalidate
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            True if successful
        """
        # Delete session from Redis
        await cache_service.delete(CacheNamespace.ADMIN_SESSION, session_id)
        
        await self._audit_repo.create_log(
            action=AuditAction.LOGOUT,
            admin_id=admin_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"session_id": session_id},
            severity="INFO",
            success=True,
        )
        
        logger.info("admin_logged_out", admin_id=str(admin_id))
        return True
    
    async def refresh_token(
        self,
        refresh_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Refresh access token using refresh token.
        
        Args:
            refresh_token: Valid refresh token
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            New access token
            
        Raises:
            AuthenticationException: If refresh token is invalid
        """
        try:
            new_tokens = refresh_jwt_token(refresh_token)
            
            # Generate new CSRF token
            session_id = generate_secure_token(16)
            csrf_token = generate_csrf_token(session_id)
            
            return {
                "access_token": new_tokens["access_token"],
                "token_type": "bearer",
                "expires_in": new_tokens["expires_in"],
                "csrf_token": csrf_token,
            }
            
        except Exception as e:
            logger.warning("token_refresh_failed", error=str(e))
            raise AuthenticationException(
                "Invalid refresh token",
                code=ErrorCode.INVALID_CREDENTIALS
            )
    
    async def validate_session(
        self,
        session_id: str,
        csrf_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Validate an admin session.
        
        Args:
            session_id: Session ID from token
            csrf_token: CSRF token to validate
            
        Returns:
            Session data if valid, None otherwise
        """
        session_data = await cache_service.hgetall(
            CacheNamespace.ADMIN_SESSION,
            session_id,
        )
        
        if not session_data:
            return None
        
        if csrf_token:
            stored_csrf = session_data.get("csrf_token")
            if not stored_csrf or stored_csrf != csrf_token:
                return None
        
        return session_data
    
    # =========================================================================
    # TWO-FACTOR AUTHENTICATION
    # =========================================================================
    
    async def enable_2fa(
        self,
        admin_id: UUID,
        password: str,
    ) -> Dict[str, Any]:
        """
        Enable 2FA for an admin user.
        
        Args:
            admin_id: Admin user ID
            password: Current password for confirmation
            
        Returns:
            2FA setup data with secret and QR code URI
            
        Raises:
            AuthenticationException: If password is invalid
        """
        admin = await self._admin_repo.get_by_id(admin_id)
        
        if not admin:
            raise NotFoundException("AdminUser", str(admin_id))
        
        # Verify password
        if not verify_password(admin.password_hash, password):
            raise AuthenticationException("Invalid password")
        
        # Check if 2FA already enabled
        if admin.two_factor_enabled:
            raise ValidationException("2FA is already enabled")
        
        # Generate TOTP secret
        secret = generate_totp_secret()
        qr_code_uri = generate_totp_uri(secret, admin.email)
        
        # Generate backup codes
        backup_codes = generate_backup_codes(8)
        
        # Store in temporary cache for verification
        temp_token = generate_secure_token(32)
        await cache_service.set(
            CacheNamespace.TWO_FACTOR_SESSION,
            f"setup:{temp_token}",
            {
                "admin_id": str(admin_id),
                "secret": secret,
                "backup_codes": backup_codes,
            },
            ttl=600,  # 10 minutes
        )
        
        logger.info("2fa_setup_initiated", admin_id=str(admin_id))
        
        return {
            "temp_token": temp_token,
            "secret": secret,
            "qr_code_uri": qr_code_uri,
            "backup_codes": backup_codes,
            "message": "Scan QR code with Google Authenticator or Authy",
        }
    
    async def verify_and_enable_2fa(
        self,
        admin_id: UUID,
        temp_token: str,
        two_factor_code: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Verify 2FA setup and enable it.
        
        Args:
            admin_id: Admin user ID
            temp_token: Temporary token from enable_2fa
            two_factor_code: TOTP code to verify
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            True if enabled successfully
            
        Raises:
            AuthenticationException: If verification fails
        """
        # Get setup data
        setup_data = await cache_service.get(
            CacheNamespace.TWO_FACTOR_SESSION,
            f"setup:{temp_token}",
        )
        
        if not setup_data:
            raise AuthenticationException("Setup session expired")
        
        if setup_data["admin_id"] != str(admin_id):
            raise AuthenticationException("Invalid setup session")
        
        # Verify TOTP code
        secret = setup_data["secret"]
        if not verify_totp(secret, two_factor_code):
            raise AuthenticationException("Invalid 2FA code")
        
        # Enable 2FA
        backup_codes = setup_data["backup_codes"]
        encrypted_secret = encrypt_field(secret)
        
        success = await self._admin_repo.enable_2fa(
            admin_id=admin_id,
            secret=encrypted_secret,
            backup_codes=backup_codes,
        )
        
        if success:
            # Clean up temp data
            await cache_service.delete(
                CacheNamespace.TWO_FACTOR_SESSION,
                f"setup:{temp_token}",
            )
            
            await self._audit_repo.create_log(
                action=AuditAction.TWO_FACTOR_ENABLED,
                admin_id=admin_id,
                ip_address=ip_address,
                user_agent=user_agent,
                severity="INFO",
                success=True,
            )
            
            logger.info("2fa_enabled", admin_id=str(admin_id))
        
        return success
    
    async def disable_2fa(
        self,
        admin_id: UUID,
        password: str,
        two_factor_code: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Disable 2FA for an admin user.
        
        Args:
            admin_id: Admin user ID
            password: Current password
            two_factor_code: 2FA code (required if 2FA is still functional)
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            True if disabled
        """
        admin = await self._admin_repo.get_by_id(admin_id)
        
        if not admin:
            raise NotFoundException("AdminUser", str(admin_id))
        
        # Verify password
        if not verify_password(admin.password_hash, password):
            raise AuthenticationException("Invalid password")
        
        # If 2FA is enabled and functional, verify code
        if admin.two_factor_enabled and two_factor_code:
            secret = decrypt_field(admin.two_factor_secret)
            is_valid_totp = verify_totp(secret, two_factor_code)
            
            is_valid_backup = False
            if not is_valid_totp and admin.backup_codes:
                is_valid_backup, _ = verify_backup_code(admin.backup_codes, two_factor_code)
            
            if not is_valid_totp and not is_valid_backup:
                raise AuthenticationException("Invalid 2FA code")
        
        # Disable 2FA
        success = await self._admin_repo.disable_2fa(admin_id)
        
        if success:
            await self._audit_repo.create_log(
                action=AuditAction.TWO_FACTOR_DISABLED,
                admin_id=admin_id,
                ip_address=ip_address,
                user_agent=user_agent,
                severity="WARN",
                success=True,
            )
            
            logger.info("2fa_disabled", admin_id=str(admin_id))
        
        return success
    
    async def regenerate_backup_codes(
        self,
        admin_id: UUID,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> List[str]:
        """
        Regenerate backup codes for an admin.
        
        Args:
            admin_id: Admin user ID
            password: Current password
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            List of new backup codes
        """
        admin = await self._admin_repo.get_by_id(admin_id)
        
        if not admin:
            raise NotFoundException("AdminUser", str(admin_id))
        
        # Verify password
        if not verify_password(admin.password_hash, password):
            raise AuthenticationException("Invalid password")
        
        # Regenerate codes
        new_codes = await self._admin_repo.regenerate_backup_codes(admin_id)
        
        await self._audit_repo.create_log(
            action=AuditAction.CONFIG_CHANGE,
            admin_id=admin_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"change": "backup_codes_regenerated"},
            severity="INFO",
            success=True,
        )
        
        logger.info("backup_codes_regenerated", admin_id=str(admin_id))
        
        return new_codes
    
    # =========================================================================
    # PASSWORD MANAGEMENT
    # =========================================================================
    
    async def change_password(
        self,
        admin_id: UUID,
        current_password: str,
        new_password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Change admin password.
        
        Args:
            admin_id: Admin user ID
            current_password: Current password
            new_password: New password
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            True if changed
        """
        admin = await self._admin_repo.get_by_id(admin_id)
        
        if not admin:
            raise NotFoundException("AdminUser", str(admin_id))
        
        # Verify current password
        if not verify_password(admin.password_hash, current_password):
            raise AuthenticationException("Invalid current password")
        
        # Validate new password strength
        is_valid, issues = validate_password_strength(new_password)
        if not is_valid:
            raise ValidationException(
                "Password does not meet strength requirements",
                details={"issues": issues}
            )
        
        # Update password
        success = await self._admin_repo.update_password(admin_id, new_password)
        
        if success:
            # Invalidate all sessions for this user
            # (Implementation would scan and delete Redis sessions)
            
            await self._audit_repo.create_log(
                action=AuditAction.PASSWORD_CHANGED,
                admin_id=admin_id,
                ip_address=ip_address,
                user_agent=user_agent,
                severity="WARN",
                success=True,
            )
            
            logger.info("password_changed", admin_id=str(admin_id))
        
        return success
    
    # =========================================================================
    # USER MANAGEMENT
    # =========================================================================
    
    async def create_admin(
        self,
        created_by: UUID,
        email: str,
        password: str,
        full_name: str,
        role: AdminRole = AdminRole.VIEWER,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new admin user.
        
        Args:
            created_by: Admin ID of creator
            email: New admin email
            password: Initial password
            full_name: Full name
            role: Admin role
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            Created admin data
        """
        # Check permissions
        creator = await self._admin_repo.get_by_id(created_by)
        if not creator or not creator.has_permission(AdminRole.ADMIN):
            raise AuthorizationException("Insufficient permissions to create admin")
        
        # Validate email
        if not validate_email(email):
            raise ValidationException("Invalid email format")
        
        # Check if email already exists
        existing = await self._admin_repo.get_by_email(email)
        if existing:
            raise ValidationException("Email already registered")
        
        # Validate password
        is_valid, issues = validate_password_strength(password)
        if not is_valid:
            raise ValidationException(
                "Password does not meet strength requirements",
                details={"issues": issues}
            )
        
        # Create admin
        admin = await self._admin_repo.create_admin(
            email=email,
            password=password,
            full_name=full_name,
            role=role,
        )
        
        await self._audit_repo.create_log(
            action=AuditAction.USER_CREATED,
            admin_id=created_by,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "created_user_id": str(admin.id),
                "created_email": email,
                "role": role.value,
            },
            severity="WARN",
            success=True,
        )
        
        logger.info("admin_created", created_by=str(created_by), new_admin=str(admin.id))
        
        return {
            "id": str(admin.id),
            "email": admin.email,
            "full_name": admin.full_name,
            "role": admin.role,
            "is_active": admin.is_active,
            "created_at": admin.created_at.isoformat(),
        }
    
    async def update_admin(
        self,
        admin_id: UUID,
        updated_by: UUID,
        full_name: Optional[str] = None,
        role: Optional[AdminRole] = None,
        is_active: Optional[bool] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update an admin user.
        
        Args:
            admin_id: Admin to update
            updated_by: Admin performing update
            full_name: New full name
            role: New role
            is_active: New active status
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            Updated admin data
        """
        # Check permissions
        updater = await self._admin_repo.get_by_id(updated_by)
        if not updater:
            raise AuthorizationException("Updater not found")
        
        # Cannot modify superadmin unless you are superadmin
        target = await self._admin_repo.get_by_id(admin_id)
        if not target:
            raise NotFoundException("AdminUser", str(admin_id))
        
        if target.role == AdminRole.SUPERADMIN.value and updater.role != AdminRole.SUPERADMIN.value:
            raise AuthorizationException("Cannot modify superadmin")
        
        if not updater.has_permission(AdminRole.ADMIN):
            raise AuthorizationException("Insufficient permissions")
        
        # Build update data
        update_data = {}
        changes = {}
        
        if full_name is not None:
            update_data["full_name"] = full_name
            changes["full_name"] = full_name
        
        if role is not None:
            # Only superadmin can assign superadmin role
            if role == AdminRole.SUPERADMIN and updater.role != AdminRole.SUPERADMIN.value:
                raise AuthorizationException("Only superadmin can assign superadmin role")
            update_data["role"] = role.value
            changes["role"] = role.value
        
        if is_active is not None:
            update_data["is_active"] = is_active
            changes["is_active"] = is_active
        
        if not update_data:
            return target.to_dict()
        
        # Update
        updated = await self._admin_repo.update(admin_id, update_data)
        
        await self._audit_repo.create_log(
            action=AuditAction.USER_UPDATED,
            admin_id=updated_by,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "updated_user_id": str(admin_id),
                "changes": changes,
            },
            severity="WARN",
            success=True,
        )
        
        logger.info("admin_updated", updated_by=str(updated_by), target=str(admin_id))
        
        return updated.to_dict() if updated else {}
    
    async def get_admin(self, admin_id: UUID) -> Dict[str, Any]:
        """
        Get admin user by ID.
        
        Args:
            admin_id: Admin user ID
            
        Returns:
            Admin data with permissions
        """
        admin = await self._admin_repo.get_by_id(admin_id)
        
        if not admin:
            raise NotFoundException("AdminUser", str(admin_id))
        
        data = admin.to_dict()
        data["permissions"] = self.ROLE_PERMISSIONS.get(admin.role, [])
        
        return data
    
    async def list_admins(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List all admin users.
        
        Args:
            skip: Pagination offset
            limit: Maximum results
            
        Returns:
            Tuple of (admins, total_count)
        """
        admins = await self._admin_repo.get_all(skip=skip, limit=limit)
        total = await self._admin_repo.count()
        
        admin_list = []
        for admin in admins:
            data = admin.to_dict()
            data["permissions"] = self.ROLE_PERMISSIONS.get(admin.role, [])
            admin_list.append(data)
        
        return admin_list, total
    
    async def deactivate_admin(
        self,
        admin_id: UUID,
        deactivated_by: UUID,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Deactivate an admin user.
        
        Args:
            admin_id: Admin to deactivate
            deactivated_by: Admin performing deactivation
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            True if deactivated
        """
        # Check permissions
        deactivator = await self._admin_repo.get_by_id(deactivated_by)
        if not deactivator or not deactivator.has_permission(AdminRole.ADMIN):
            raise AuthorizationException("Insufficient permissions")
        
        # Cannot deactivate self
        if admin_id == deactivated_by:
            raise ValidationException("Cannot deactivate your own account")
        
        # Cannot deactivate superadmin unless superadmin
        target = await self._admin_repo.get_by_id(admin_id)
        if target and target.role == AdminRole.SUPERADMIN.value:
            if deactivator.role != AdminRole.SUPERADMIN.value:
                raise AuthorizationException("Cannot deactivate superadmin")
        
        success = await self._admin_repo.deactivate_admin(admin_id)
        
        if success:
            await self._audit_repo.create_log(
                action=AuditAction.USER_DELETED,
                admin_id=deactivated_by,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"deactivated_user_id": str(admin_id)},
                severity="CRITICAL",
                success=True,
            )
            
            logger.info("admin_deactivated", deactivated_by=str(deactivated_by), target=str(admin_id))
        
        return success
    
    # =========================================================================
    # AUDIT LOGS
    # =========================================================================
    
    async def get_audit_logs(
        self,
        admin_id: Optional[UUID] = None,
        action: Optional[str] = None,
        severity: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get audit logs with filters.
        
        Returns:
            Tuple of (logs, total_count)
        """
        logs, total = await self._audit_repo.search_logs(
            admin_id=admin_id,
            action=action,
            severity=severity,
            start_date=start_date,
            end_date=end_date,
            skip=skip,
            limit=limit,
        )
        
        log_list = [log.to_dict() for log in logs]
        
        return log_list, total
    
    def has_permission(self, role: str, permission: str) -> bool:
        """
        Check if a role has a specific permission.
        
        Args:
            role: Admin role
            permission: Permission to check
            
        Returns:
            True if role has permission
        """
        permissions = self.ROLE_PERMISSIONS.get(role, [])
        return permission in permissions
    
    def get_permissions_for_role(self, role: str) -> List[str]:
        """
        Get all permissions for a role.
        
        Args:
            role: Admin role
            
        Returns:
            List of permissions
        """
        return self.ROLE_PERMISSIONS.get(role, [])