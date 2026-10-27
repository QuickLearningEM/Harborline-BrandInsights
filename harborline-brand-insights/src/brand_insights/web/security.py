"""Security headers, CSRF tokens, and session helpers."""

import hmac
import secrets
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .auth import User, UserStore

CSP = (
    "default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self' data:; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, hsts: bool = False):
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h["Content-Security-Policy"] = CSP
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        if not request.url.path.startswith("/static/"):
            h["Cache-Control"] = "no-store"
        if self.hsts:
            h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


def ensure_csrf(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = request.session["csrf"] = secrets.token_urlsafe(32)
    return token


def verify_csrf(request: Request, submitted: str) -> bool:
    expected = request.session.get("csrf", "")
    return bool(expected) and hmac.compare_digest(expected, submitted or "")


def start_session(request: Request, user: User) -> None:
    request.session.clear()  # never reuse a pre-login session
    now = int(time.time())
    request.session.update({
        "user": user.username, "iat": now, "seen": now, "csrf": secrets.token_urlsafe(32),
    })


def current_user(request: Request, users: UserStore, max_age: int,
                 idle_timeout: int = 0) -> User | None:
    """The signed-in user, or None. Re-checks the account on every request so disabled
    users lose access immediately, and enforces server-side absolute and idle lifetimes."""
    name, issued = request.session.get("user"), request.session.get("iat", 0)
    if not name:
        return None
    now = int(time.time())
    idle = now - request.session.get("seen", issued)
    if now - issued > max_age or (idle_timeout and idle > idle_timeout):
        request.session.clear()
        return None
    user = users.get(name)
    if user:
        request.session["seen"] = now
    return user
