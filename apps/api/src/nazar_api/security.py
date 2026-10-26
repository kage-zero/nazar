"""Password hashing, server-side sessions, login throttling and the CSRF header rule."""

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from nazar_api.models import AuthSession, User, utcnow

SESSION_COOKIE = "nazar_session"
CSRF_HEADER = "x-nazar-request"
"""State-changing requests must carry this header. Browsers cannot attach custom headers to
cross-site form posts, and cross-origin fetches with it need a CORS preflight we refuse."""

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    b64 = base64.b64encode
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = encoded.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User, days: int) -> str:
    token = secrets.token_urlsafe(32)
    db.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
    db.add(
        AuthSession(
            token_hash=_token_hash(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(days=days),
        )
    )
    db.commit()
    return token


def user_for_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = db.execute(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == _token_hash(token), AuthSession.expires_at > utcnow())
    ).scalar_one_or_none()
    return row


def end_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
        db.commit()


class LoginThrottle:
    """In-memory sliding window of failed logins per (client, email)."""

    def __init__(self, max_failures: int = 8, window_s: float = 900) -> None:
        self.max_failures = max_failures
        self.window_s = window_s
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, key: str) -> deque[float]:
        q = self._failures[key]
        cutoff = time.monotonic() - self.window_s
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.max_failures

    def fail(self, key: str) -> None:
        self._recent(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
