"""Admin interface routes - Jinja2 templates."""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.api.dependencies.auth import get_current_admin
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Setup Jinja2 templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


from app.admin.i18n import get_translations

def render_template(name: str, context: dict):
    request = context.get("request")
    lang = request.cookies.get("admin_lang", "en")
    t = get_translations(lang)
    ctx = {"lang": lang, "t": t}
    ctx.update(context)
    return templates.TemplateResponse(name, ctx)

@router.get("/set-lang")
async def set_lang(lang: str, request: Request):
    referer = request.headers.get("referer", "/admin/dashboard")
    response = RedirectResponse(url=referer, status_code=303)
    response.set_cookie("admin_lang", lang, max_age=31536000, path="/")
    return response


# =============================================================================
# Authentication pages (no auth required)
# =============================================================================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return render_template("auth/login.html", {"request": request})


@router.get("/verify-2fa", response_class=HTMLResponse)
async def verify_2fa_page(request: Request):
    """2FA verification page."""
    return render_template("auth/verify_2fa.html", {"request": request})


# =============================================================================
# Protected pages (auth required)
# =============================================================================

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, admin: dict = Depends(get_current_admin)):
    """Dashboard page."""
    return render_template("dashboard/index.html", {
        "request": request,
        "admin": admin
    })


# ─────────────────────────────────────────────────────────────────────────────
# Users management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
async def users_list_page(request: Request, admin: dict = Depends(get_current_admin)):
    """List of admin users."""
    return render_template("users/list.html", {
        "request": request,
        "admin": admin
    })


@router.get("/users/create", response_class=HTMLResponse)
async def user_create_page(request: Request, admin: dict = Depends(get_current_admin)):
    """Create new admin user page."""
    return render_template("users/create.html", {
        "request": request,
        "admin": admin
    })


@router.get("/users/edit/{user_id}", response_class=HTMLResponse)
async def user_edit_page(request: Request, user_id: str, admin: dict = Depends(get_current_admin)):
    """Edit admin user page."""
    return render_template("users/edit.html", {
        "request": request,
        "admin": admin,
        "user_id": user_id
    })


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/knowledge", response_class=HTMLResponse)
async def knowledge_list_page(request: Request, admin: dict = Depends(get_current_admin)):
    """List of knowledge documents."""
    return render_template("knowledge/list.html", {
        "request": request,
        "admin": admin
    })


@router.get("/knowledge/upload", response_class=HTMLResponse)
async def knowledge_upload_page(request: Request, admin: dict = Depends(get_current_admin)):
    """Upload new document page."""
    return render_template("knowledge/upload.html", {
        "request": request,
        "admin": admin
    })


@router.get("/knowledge/detail/{doc_id}", response_class=HTMLResponse)
async def knowledge_detail_page(request: Request, doc_id: str, admin: dict = Depends(get_current_admin)):
    """Document detail page."""
    return render_template("knowledge/detail.html", {
        "request": request,
        "admin": admin,
        "doc_id": doc_id
    })


# ─────────────────────────────────────────────────────────────────────────────
# Conversations
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/conversations", response_class=HTMLResponse)
async def conversations_list_page(request: Request, admin: dict = Depends(get_current_admin)):
    """List of conversations."""
    return render_template("conversations/list.html", {
        "request": request,
        "admin": admin
    })


@router.get("/conversations/detail/{conv_id}", response_class=HTMLResponse)
async def conversation_detail_page(request: Request, conv_id: str, admin: dict = Depends(get_current_admin)):
    """Conversation detail page."""
    return render_template("conversations/detail.html", {
        "request": request,
        "admin": admin,
        "conv_id": conv_id
    })


# ─────────────────────────────────────────────────────────────────────────────
# Audit logs
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/audit", response_class=HTMLResponse)
async def audit_logs_page(request: Request, admin: dict = Depends(get_current_admin)):
    """Audit logs page."""
    return render_template("audit/logs.html", {
        "request": request,
        "admin": admin
    })


# ─────────────────────────────────────────────────────────────────────────────
# Logout
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/logout")
async def logout_page(request: Request):
    """Logout and redirect to login."""
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    response.delete_cookie("csrf_token")
    return response
