"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..config import Settings, get_settings
from ..warehouse import Warehouse, get_warehouse
from .auth import LoginThrottle, UserStore
from .dashboard import DashboardService
from .routes import router
from .security import SecurityHeadersMiddleware


def create_app(settings: Settings | None = None, warehouse: Warehouse | None = None) -> FastAPI:
    settings = settings or get_settings()
    # No interactive API docs or OpenAPI schema are exposed.
    app = FastAPI(title="Harborline brand insights", docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.state.settings = settings
    app.state.users = UserStore(settings.auth_db_path)
    app.state.throttle = LoginThrottle(settings.login_max_failures, settings.login_lockout_seconds)
    app.state.dashboard = DashboardService(
        warehouse or get_warehouse(settings), settings.dashboard_cache_seconds
    )

    # Added innermost to outermost: session, then security headers, then host check.
    app.add_middleware(
        SessionMiddleware, secret_key=settings.session_secret_or_dev(), session_cookie="bi_session",
        max_age=settings.session_max_age_seconds, same_site="lax",
        https_only=settings.is_production or settings.secure_cookies,
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.host_list)

    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
    app.include_router(router)
    return app
