import re

import pytest
from fastapi.testclient import TestClient

from brand_insights.config import Settings
from brand_insights.web.app import create_app
from brand_insights.web.auth import UserStore

PASSWORD = "correct horse battery staple"


@pytest.fixture
def client(built, settings):
    UserStore(settings.auth_db_path).create_user("analyst", PASSWORD)
    return TestClient(create_app(settings, built))


def _csrf(client):
    html = client.get("/login").text
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _login(client, password=PASSWORD, username="analyst"):
    return client.post("/login", data={"username": username, "password": password,
                                       "csrf_token": _csrf(client)}, follow_redirects=False)


def test_dashboard_requires_login(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert client.get("/api/scorecard").status_code == 401


def test_login_and_dashboard(client):
    assert _login(client).status_code == 303
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Established Homeowners" in page.text and "Under-invested" in page.text
    assert len(client.get("/api/scorecard").json()["segments"]) == 5


def test_wrong_password_and_unknown_user_look_identical(client):
    a, b = _login(client, "wrong password here"), _login(client, username="nobody")
    assert a.status_code == b.status_code == 401
    assert "incorrect" in a.text and "incorrect" in b.text


def test_post_without_csrf_is_rejected(client):
    r = client.post("/login", data={"username": "analyst", "password": PASSWORD})
    assert r.status_code == 400
    client.get("/login")
    assert client.post("/login", data={"username": "analyst", "password": PASSWORD,
                                       "csrf_token": "forged"}).status_code == 400


def test_lockout_after_repeated_failures(client):
    for _ in range(5):
        assert _login(client, "bad password 123").status_code == 401
    assert _login(client).status_code == 429  # even the right password is locked out


def test_logout_ends_session(client):
    _login(client)
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/dashboard").text).group(1)
    assert client.post("/logout", data={"csrf_token": token}, follow_redirects=False).status_code == 303
    assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_security_headers(client):
    h = client.get("/login").headers
    assert "script-src 'none'" in h["content-security-policy"]
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["x-frame-options"] == "DENY" and h["cache-control"] == "no-store"
    assert h["x-content-type-options"] == "nosniff"


def test_no_api_docs_exposed(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_untrusted_host_rejected(client):
    assert client.get("/healthz", headers={"host": "evil.example"}).status_code == 400


def test_production_requires_strong_secret():
    with pytest.raises(ValueError):
        Settings(environment="production", session_secret="short")
    with pytest.raises(ValueError):
        Settings(environment="production", session_secret="x" * 40, allowed_hosts="*")


def test_weak_password_rejected(settings):
    with pytest.raises(ValueError):
        UserStore(settings.auth_db_path).create_user("someone", "short")


def test_idle_session_expires(client, monkeypatch):
    import brand_insights.web.security as sec

    _login(client)
    now = sec.time.time()
    monkeypatch.setattr(sec.time, "time", lambda: now + 31 * 60)
    assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_activity_keeps_session_alive(client, monkeypatch):
    import brand_insights.web.security as sec

    _login(client)
    now = sec.time.time()
    for minutes in (20, 40):  # each visit is within the 30-minute idle window
        monkeypatch.setattr(sec.time, "time", lambda m=minutes: now + m * 60)
        assert client.get("/dashboard", follow_redirects=False).status_code == 200


def test_secure_cookie_flag(built, tmp_path):
    s = Settings(_env_file=None, sqlite_path=tmp_path / "wh.db",
                 auth_db_path=tmp_path / "auth.db",
                 session_secret="x" * 40, secure_cookies=True)
    r = TestClient(create_app(s, built)).get("/login")
    assert "secure" in r.headers["set-cookie"].lower()
