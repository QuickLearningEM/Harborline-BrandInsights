"""User accounts, password hashing, and login throttling.

Passwords are hashed with Argon2id. Unknown usernames still trigger a hash check so response
time does not reveal which accounts exist. For production at scale, replace this module with
single sign-on (OIDC) from Harborline's identity provider; the rest of the app only needs
`current_user`.
"""

import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

log = logging.getLogger(__name__)

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("timing-equalizer-not-a-real-password")
_USERNAME_RE = re.compile(r"^[a-z0-9._@-]{3,64}$")
MIN_PASSWORD_LENGTH = 12


@dataclass(frozen=True)
class User:
    username: str
    role: str


class UserStore:
    def __init__(self, path: Path | str):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS users ("
                "username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, "
                "role TEXT NOT NULL DEFAULT 'viewer', disabled INTEGER NOT NULL DEFAULT 0, "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def create_user(self, username: str, password: str, role: str = "viewer") -> None:
        username = username.strip().lower()
        if not _USERNAME_RE.match(username):
            raise ValueError("Username must be 3-64 characters: letters, digits, . _ @ -")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
        if role not in {"viewer", "admin"}:
            raise ValueError("Role must be viewer or admin")
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, _hasher.hash(password), role),
            )

    def get(self, username: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT username, role, disabled FROM users WHERE username = ?",
                (username.strip().lower(),),
            ).fetchone()
        return User(row[0], row[1]) if row and not row[2] else None

    def verify(self, username: str, password: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT username, password_hash, role, disabled FROM users WHERE username = ?",
                (username.strip().lower(),),
            ).fetchone()
        stored = row[1] if row else _DUMMY_HASH
        try:
            _hasher.verify(stored, password)
        except (VerifyMismatchError, InvalidHashError):
            return None
        if not row or row[3]:
            return None
        if _hasher.check_needs_rehash(stored):
            self.create_user(row[0], password, row[2])
        return User(row[0], row[2])


class LoginThrottle:
    """Locks a client+username pair after repeated failures. In-memory: use Redis if the app
    runs on more than one instance."""

    def __init__(self, max_failures: int = 5, lockout_seconds: int = 900):
        self.max_failures, self.lockout_seconds = max_failures, lockout_seconds
        self._failures: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        cutoff = time.monotonic() - self.lockout_seconds
        recent = [t for t in self._failures.get(key, []) if t > cutoff]
        self._failures[key] = recent
        return recent

    def is_locked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.max_failures

    def record_failure(self, key: str) -> None:
        self._recent(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
