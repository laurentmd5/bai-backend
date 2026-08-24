"""
Admin authentication endpoints for Company Bot.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.models.request.admin import (
    AdminLoginRequest,
    AdminLogin2FARequest,
    AdminRefreshTokenRequest,
    AdminChangePasswordRequest,
)
from app.models.response.admin import (
    TokenResponse,
    AdminLoginResponse,
    AdminUserResponse,
)
from app.services.admin_service import AdminService
from app.api.dependencies.auth import get_current_admin, get_admin_service
from app.middleware.csrf import generate_csrf_token, add_csrf_cookie
from app.services.cache.redis_cache import cache_service, CacheNamespace
from app.core.exceptions import AuthenticationException, AccountLockedException
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Admin Authentication"])

# Failed-login lockout configuration
_MAX_FAILURES   = 5    # max consecutive failures before lockout
_LOCKOUT_TTL    = 900  # lockout duration in seconds (15 min)
_FAILURES_TTL   = 900  # sliding window for counting failures


def _ip_key(ip: str) -> str:
    return ip.replace(":", "_")  # IPv6-safe


async def _check_lockout(ip: str) -> None:
    """Raise 429 if the IP is currently locked out. Fails open on cache errors."""
    try:
        locked = await cache_service.get(CacheNamespace.LOGIN_FAILURES, _ip_key(ip), "locked")
        if locked:
            remaining = await cache_service.ttl(CacheNamespace.LOGIN_FAILURES, _ip_key(ip), "locked")
            raise HTTPException(
                status_code=429,
                detail="Trop de tentatives de connexion échouées. Réessayez plus tard.",
                headers={"Retry-After": str(max(remaining, 1))},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.debug("login_lockout_check_failed", error=str(e))  # fail open


async def _record_failure(ip: str) -> int:
    """Increment the failure counter; lock out if threshold reached. Fails open on cache errors."""
    try:
        count = await cache_service.incr(
            CacheNamespace.LOGIN_FAILURES, _ip_key(ip), "count",
            ttl=_FAILURES_TTL,
        )
        if count >= _MAX_FAILURES:
            await cache_service.set(
                CacheNamespace.LOGIN_FAILURES, _ip_key(ip), "locked",
                value={"locked_at": "now"},
                ttl=_LOCKOUT_TTL,
            )
            logger.warning("login_ip_locked_out", ip=ip, failures=count)
        return count
    except Exception as e:
        logger.debug("login_failure_record_failed", error=str(e))
        return 0  # fail open — don't know how many failures


async def _clear_failures(ip: str) -> None:
    """Clear failure state after a successful login. Fails open on cache errors."""
    try:
        await cache_service.delete(CacheNamespace.LOGIN_FAILURES, _ip_key(ip), "count")
        await cache_service.delete(CacheNamespace.LOGIN_FAILURES, _ip_key(ip), "locked")
    except Exception:
        pass  # fail open


@router.get("/csrf-token")
async def get_csrf_token(request: Request):
    """
    Get a CSRF token for form submissions.

    Returns a new CSRF token that must be included in the X-CSRF-Token header
    for all state-changing requests (POST, PUT, DELETE, PATCH).
    """
    token = await generate_csrf_token()
    response = JSONResponse({"csrf_token": token})
    add_csrf_cookie(response, token)
    logger.debug("csrf_token_issued", client_ip=request.client.host if request.client else None)
    return response


@router.post("/login", response_model=AdminLoginResponse)
async def login(
    request: Request,
    login_data: AdminLoginRequest,
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminLoginResponse:
    """
    Admin login — first step.

    Rate-limited per IP: max 5 failed attempts within 15 minutes trigger a lockout.
    Returns tokens if 2FA is not enabled, or session_token if 2FA is required.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent")

    # ── IP-based lockout check ───────────────────────────────────
    await _check_lockout(client_ip)

    try:
        result = await admin_service.login(
            email=login_data.email,
            password=login_data.password,
            ip_address=client_ip,
            user_agent=user_agent,
        )
        # Successful login → clear any previous failure counters
        await _clear_failures(client_ip)
        return AdminLoginResponse(**result)

    except AccountLockedException:
        # Account-level lockout (DB-side) — don't increment IP counter
        raise HTTPException(
            status_code=423,
            detail="Compte verrouillé en raison de trop de tentatives échouées.",
        )

    except AuthenticationException as exc:
        # Wrong credentials → track per-IP failures
        failure_count = await _record_failure(client_ip)
        remaining = max(_MAX_FAILURES - failure_count, 0)

        if failure_count >= _MAX_FAILURES:
            raise HTTPException(
                status_code=429,
                detail="Trop de tentatives échouées. Compte verrouillé 15 minutes.",
                headers={"Retry-After": str(_LOCKOUT_TTL)},
            )

        logger.warning(
            "login_failed",
            ip=client_ip,
            email=login_data.email,
            failure_count=failure_count,
            remaining=remaining,
        )
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Email ou mot de passe incorrect",
                "remaining_attempts": remaining,
            },
        )


@router.post("/verify-2fa", response_model=TokenResponse)
async def verify_2fa(
    request: Request,
    data: AdminLogin2FARequest,
    admin_service: AdminService = Depends(get_admin_service),
) -> TokenResponse:
    """Verify 2FA code and complete login."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    result = await admin_service.verify_2fa(
        session_token=data.session_token,
        two_factor_code=data.two_factor_code,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    return TokenResponse(**result["tokens"])


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    data: AdminRefreshTokenRequest,
    admin_service: AdminService = Depends(get_admin_service),
) -> TokenResponse:
    """Refresh access token using refresh token."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    result = await admin_service.refresh_token(
        refresh_token=data.refresh_token,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    return TokenResponse(**result)


@router.post("/logout")
async def logout(
    request: Request,
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> JSONResponse:
    """Logout and invalidate session."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    await admin_service.logout(
        admin_id=current_admin["id"],
        session_id=current_admin["session_id"],
        ip_address=client_ip,
        user_agent=user_agent,
    )

    return JSONResponse(content={"message": "Logged out successfully"})


@router.get("/me", response_model=AdminUserResponse)
async def get_current_user(
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminUserResponse:
    """Get current authenticated admin user."""
    admin = await admin_service.get_admin(current_admin["id"])
    return AdminUserResponse(**admin)


@router.post("/change-password")
async def change_password(
    request: Request,
    data: AdminChangePasswordRequest,
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> JSONResponse:
    """Change admin password."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    await admin_service.change_password(
        admin_id=current_admin["id"],
        current_password=data.current_password,
        new_password=data.new_password,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    return JSONResponse(content={"message": "Password changed successfully"})

