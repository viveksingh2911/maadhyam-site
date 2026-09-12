"""Password hashing and signed-cookie sessions for the admin portal."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import settings
from .models import User, utcnow

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="admin-session")


def hash_password(password: str) -> str:
    """Hash with stdlib scrypt: `scrypt$n$r$p$salt$hash`, all base64."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    b64 = lambda raw: base64.b64encode(raw).decode("ascii")  # noqa: E731
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(hash_b64)
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


def make_session_token(user: User) -> str:
    return _serializer.dumps({"uid": user.id, "email": user.email})


def read_session_token(token: str) -> dict | None:
    try:
        return _serializer.loads(token, max_age=settings.SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return None
    user.last_login_at = utcnow()
    db.commit()
    return user


def current_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get(settings.SESSION_COOKIE)
    if not token:
        return None
    data = read_session_token(token)
    if not data:
        return None
    user = db.get(User, data.get("uid"))
    return user if user and user.is_active else None


def issue_csrf_token(request: Request) -> str:
    """Per-session CSRF token derived from the session cookie."""
    seed = request.cookies.get(settings.SESSION_COOKIE, "anonymous")
    return hmac.new(settings.SECRET_KEY.encode(), seed.encode(), hashlib.sha256).hexdigest()


def csrf_ok(request: Request, submitted: str | None) -> bool:
    return bool(submitted) and hmac.compare_digest(issue_csrf_token(request), submitted or "")
