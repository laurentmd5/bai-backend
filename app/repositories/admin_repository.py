"""
Admin repository for BARROW.AI.
Handles admin user and audit log database operations.
"""

from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy import select, func, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain.admin import AdminUser, AuditLog, AdminRole, AuditAction
from app.repositories.base import BaseRepository
from app.core.security import hash_password, generate_backup_codes, hash_backup_code
from app.core.logging import get_logger

logger = get_logger(__name__)


class AdminRepository(BaseRepository[AdminUser, Dict[str, Any], Dict[str, Any]]):
    """
    Repository for AdminUser model operations.
    """
    
    def __init__(self, session: AsyncSession):
        super().__init__(AdminUser, session)
    
    async def get_by_email(self, email: str) -> Optional[AdminUser]:
        """
        Get admin user by email.
        
        Args:
            email: Admin email address
            
        Returns:
            AdminUser instance or None
        """
        stmt = select(AdminUser).where(
            func.lower(AdminUser.email) == email.lower()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def create_admin(
        self,
        email: str,
        password: str,
        full_name: str,
        role: AdminRole = AdminRole.VIEWER,
    ) -> AdminUser:
        """
        Create a new admin user.
        
        Args:
            email: Admin email
            password: Plain text password (will be hashed)
            full_name: Full name
            role: Admin role
            
        Returns:
            Created AdminUser instance
        """
        password_hash = hash_password(password)
        
        admin = AdminUser(
            email=email.lower(),
            password_hash=password_hash,
            full_name=full_name,
            role=role.value,
            is_active=True,
            two_factor_enabled=False,
        )
        
        self.session.add(admin)
        await self.session.flush()
        await self.session.refresh(admin)
        
        logger.info(
            "admin_created",
            admin_id=str(admin.id),
            email=email,
            role=role.value
        )
        
        return admin
    
    async def update_password(
        self,
        admin_id: UUID,
        new_password: str
    ) -> bool:
        """
        Update admin password.
        
        Args:
            admin_id: Admin UUID
            new_password: New plain text password
            
        Returns:
            True if updated
        """
        password_hash = hash_password(new_password)
        
        stmt = (
            update(AdminUser)
            .where(AdminUser.id == admin_id)
            .values(
                password_hash=password_hash,
                password_changed_at=datetime.utcnow(),
                password_reset_token=None,
                password_reset_expires=None,
            )
        )
        
        result = await self.session.execute(stmt)
        await self.session.flush()
        
        updated = result.rowcount > 0
        if updated:
            logger.info("admin_password_updated", admin_id=str(admin_id))
        
        return updated
    
    async def record_login_success(
        self,
        admin_id: UUID,
        ip_address: Optional[str] = None
    ) -> None:
        """
        Record successful login.
        
        Args:
            admin_id: Admin UUID
            ip_address: Client IP address
        """
        stmt = (
            update(AdminUser)
            .where(AdminUser.id == admin_id)
            .values(
                last_login=datetime.utcnow(),
                last_ip=ip_address,
                failed_attempts=0,
                locked_until=None,
            )
        )
        
        await self.session.execute(stmt)
        await self.session.flush()
    
    async def record_login_failure(self, admin_id: UUID) -> int:
        """
        Record failed login attempt and check for lockout.
        
        Args:
            admin_id: Admin UUID
            
        Returns:
            Current failed attempts count
        """
        from app.core.config import settings
        
        # Get current failed attempts
        stmt = select(AdminUser.failed_attempts).where(AdminUser.id == admin_id)
        result = await self.session.execute(stmt)
        current = result.scalar() or 0
        
        new_count = current + 1
        update_values = {'failed_attempts': new_count}
        
        # Lock account if threshold reached
        if new_count >= settings.ADMIN_MAX_FAILED_ATTEMPTS:
            lock_until = datetime.utcnow() + timedelta(
                minutes=settings.ADMIN_LOCKOUT_MINUTES
            )
            update_values['locked_until'] = lock_until
            logger.warning(
                "admin_account_locked",
                admin_id=str(admin_id),
                attempts=new_count,
                locked_until=lock_until.isoformat()
            )
        
        stmt = (
            update(AdminUser)
            .where(AdminUser.id == admin_id)
            .values(**update_values)
        )
        
        await self.session.execute(stmt)
        await self.session.flush()
        
        return new_count
    
    async def is_locked(self, admin_id: UUID) -> bool:
        """
        Check if admin account is locked.
        
        Args:
            admin_id: Admin UUID
            
        Returns:
            True if locked
        """
        stmt = select(AdminUser.locked_until).where(AdminUser.id == admin_id)
        result = await self.session.execute(stmt)
        locked_until = result.scalar()
        
        if not locked_until:
            return False
        
        return locked_until > datetime.utcnow()
    
    async def enable_2fa(
        self,
        admin_id: UUID,
        secret: str,
        backup_codes: List[str]
    ) -> bool:
        """
        Enable 2FA for an admin user.
        
        Args:
            admin_id: Admin UUID
            secret: TOTP secret
            backup_codes: List of plain backup codes
            
        Returns:
            True if enabled
        """
        from app.core.security import encrypt_field
        
        hashed_codes = [hash_backup_code(code) for code in backup_codes]
        encrypted_secret = encrypt_field(secret)
        
        stmt = (
            update(AdminUser)
            .where(AdminUser.id == admin_id)
            .values(
                two_factor_secret=encrypted_secret,
                two_factor_enabled=True,
                backup_codes=hashed_codes,
            )
        )
        
        result = await self.session.execute(stmt)
        await self.session.flush()
        
        enabled = result.rowcount > 0
        if enabled:
            logger.info("admin_2fa_enabled", admin_id=str(admin_id))
        
        return enabled
    
    async def disable_2fa(self, admin_id: UUID) -> bool:
        """
        Disable 2FA for an admin user.
        
        Args:
            admin_id: Admin UUID
            
        Returns:
            True if disabled
        """
        stmt = (
            update(AdminUser)
            .where(AdminUser.id == admin_id)
            .values(
                two_factor_secret=None,
                two_factor_enabled=False,
                backup_codes=None,
            )
        )
        
        result = await self.session.execute(stmt)
        await self.session.flush()
        
        disabled = result.rowcount > 0
        if disabled:
            logger.info("admin_2fa_disabled", admin_id=str(admin_id))
        
        return disabled
    
    async def use_backup_code(
        self,
        admin_id: UUID,
        code_hash: str
    ) -> bool:
        """
        Mark a backup code as used.
        
        Args:
            admin_id: Admin UUID
            code_hash: Hash of the used backup code
            
        Returns:
            True if code was valid and removed
        """
        # Get current backup codes
        stmt = select(AdminUser.backup_codes).where(AdminUser.id == admin_id)
        result = await self.session.execute(stmt)
        current_codes = result.scalar() or []
        
        if code_hash not in current_codes:
            return False
        
        # Remove the used code
        new_codes = [c for c in current_codes if c != code_hash]
        
        stmt = (
            update(AdminUser)
            .where(AdminUser.id == admin_id)
            .values(backup_codes=new_codes)
        )
        
        await self.session.execute(stmt)
        await self.session.flush()
        
        logger.info("admin_backup_code_used", admin_id=str(admin_id))
        return True
    
    async def regenerate_backup_codes(self, admin_id: UUID) -> List[str]:
        """
        Generate new backup codes for an admin.
        
        Args:
            admin_id: Admin UUID
            
        Returns:
            List of new plain backup codes
        """
        new_codes = generate_backup_codes(8)
        hashed_codes = [hash_backup_code(code) for code in new_codes]
        
        stmt = (
            update(AdminUser)
            .where(AdminUser.id == admin_id)
            .values(backup_codes=hashed_codes)
        )
        
        await self.session.execute(stmt)
        await self.session.flush()
        
        logger.info("admin_backup_codes_regenerated", admin_id=str(admin_id))
        return new_codes
    
    async def get_active_admins(self) -> List[AdminUser]:
        """
        Get all active admin users.
        
        Returns:
            List of active AdminUser instances
        """
        stmt = select(AdminUser).where(AdminUser.is_active == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def deactivate_admin(self, admin_id: UUID) -> bool:
        """
        Deactivate an admin account.
        
        Args:
            admin_id: Admin UUID
            
        Returns:
            True if deactivated
        """
        stmt = (
            update(AdminUser)
            .where(AdminUser.id == admin_id)
            .values(is_active=False)
        )
        
        result = await self.session.execute(stmt)
        await self.session.flush()
        
        deactivated = result.rowcount > 0
        if deactivated:
            logger.info("admin_deactivated", admin_id=str(admin_id))
        
        return deactivated


class AuditLogRepository(BaseRepository[AuditLog, Dict[str, Any], Dict[str, Any]]):
    """
    Repository for AuditLog model operations.
    """
    
    def __init__(self, session: AsyncSession):
        super().__init__(AuditLog, session)
    
    async def create_log(
        self,
        action: AuditAction,
        admin_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "INFO",
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> AuditLog:
        """
        Create an audit log entry.
        
        Args:
            action: Action performed
            admin_id: Admin user ID
            ip_address: Client IP address
            user_agent: Client user agent
            details: Additional details
            severity: INFO, WARN, CRITICAL
            success: Whether action succeeded
            error_message: Error if failed
            
        Returns:
            Created AuditLog instance
        """
        log = AuditLog(
            action=action.value if hasattr(action, 'value') else str(action),
            admin_id=admin_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
            severity=severity,
            success=success,
            error_message=error_message,
        )
        
        self.session.add(log)
        await self.session.flush()
        await self.session.refresh(log)
        
        return log
    
    async def get_logs_by_admin(
        self,
        admin_id: UUID,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[AuditLog], int]:
        """
        Get audit logs for a specific admin.
        
        Args:
            admin_id: Admin UUID
            skip: Pagination offset
            limit: Maximum results
            
        Returns:
            Tuple of (logs, total_count)
        """
        stmt = select(AuditLog).where(AuditLog.admin_id == admin_id)
        count_stmt = select(func.count()).select_from(AuditLog).where(
            AuditLog.admin_id == admin_id
        )
        
        # Get total
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # Get logs
        stmt = stmt.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        logs = list(result.scalars().all())
        
        return logs, total
    
    async def search_logs(
        self,
        action: Optional[str] = None,
        admin_id: Optional[UUID] = None,
        severity: Optional[str] = None,
        success: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[AuditLog], int]:
        """
        Search audit logs with filters.
        
        Returns:
            Tuple of (logs, total_count)
        """
        stmt = select(AuditLog)
        count_stmt = select(func.count()).select_from(AuditLog)
        
        filters = []
        
        if action:
            filters.append(AuditLog.action == action)
        
        if admin_id:
            filters.append(AuditLog.admin_id == admin_id)
        
        if severity:
            filters.append(AuditLog.severity == severity)
        
        if success is not None:
            filters.append(AuditLog.success == success)
        
        if start_date:
            filters.append(AuditLog.created_at >= start_date)
        
        if end_date:
            filters.append(AuditLog.created_at <= end_date)
        
        if filters:
            stmt = stmt.where(and_(*filters))
            count_stmt = count_stmt.where(and_(*filters))
        
        # Get total
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # Get logs
        stmt = stmt.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        logs = list(result.scalars().all())
        
        return logs, total
    
    async def get_recent_failed_logins(
        self,
        ip_address: Optional[str] = None,
        minutes: int = 30
    ) -> int:
        """
        Count recent failed login attempts.
        
        Args:
            ip_address: Optional IP filter
            minutes: Time window in minutes
            
        Returns:
            Number of failed attempts
        """
        since = datetime.utcnow() - timedelta(minutes=minutes)
        
        stmt = select(func.count()).select_from(AuditLog).where(
            and_(
                AuditLog.action == AuditAction.LOGIN_FAILED.value,
                AuditLog.created_at >= since
            )
        )
        
        if ip_address:
            stmt = stmt.where(AuditLog.ip_address == ip_address)
        
        result = await self.session.execute(stmt)
        return result.scalar() or 0