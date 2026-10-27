"""HTTP routes. Every page except /login and /healthz requires a signed-in user."""

import logging
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .security import current_user, ensure_csrf, start_session, verify_csrf

log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()


def _user(request: Request):
    s = request.app.state
    return current_user(request, s.users, s.settings.session_max_age_seconds,
                        s.settings.session_idle_seconds)


def _login_page(request: Request, error: str | None = None, status: int = 200):
    return templates.TemplateResponse(
        request, "login.html", {"csrf_token": ensure_csrf(request), "error": error},
        status_code=status,
    )


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/")
def index():
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/login")
def login_form(request: Request):
    if _user(request):
        return RedirectResponse("/dashboard", status_code=303)
    return _login_page(request)


@router.post("/login")
def login(request: Request, username: str = Form(""), password: str = Form(""),
          csrf_token: str = Form("")):
    state = request.app.state
    if not verify_csrf(request, csrf_token):
        return _login_page(request, "Your session expired. Try signing in again.", 400)
    ip = request.client.host if request.client else "unknown"
    key = f"{ip}:{username.strip().lower()[:64]}"
    if state.throttle.is_locked(key):
        log.warning("Login locked out for %s", key)
        return _login_page(request, "Too many failed attempts. Try again in 15 minutes.", 429)
    user = state.users.verify(username, password)
    if not user:
        state.throttle.record_failure(key)
        log.warning("Failed login for %s", key)
        return _login_page(request, "Username or password is incorrect.", 401)
    state.throttle.reset(key)
    start_session(request, user)
    log.info("User %s signed in", user.username)
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form("")):
    if verify_csrf(request, csrf_token):
        request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/dashboard")
def dashboard(request: Request):
    user = _user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    ctx = request.app.state.dashboard.get()
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"user": user, "csrf_token": ensure_csrf(request), "data": ctx},
    )


@router.get("/api/scorecard")
def scorecard_json(request: Request):
    if not _user(request):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    ctx = request.app.state.dashboard.get()
    return JSONResponse({"segments": ctx["rows"] if ctx else []})
