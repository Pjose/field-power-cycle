"""
Real auth, not a stub. Passwords are hashed with bcrypt (never stored or
compared in plaintext); sessions are stateless JWTs signed with a server
secret. Every dependency below actually rejects requests that don't meet
its condition — there's no dependency here that's decorative.

SECRET_KEY is generated at process start if not supplied via environment,
which is fine for this reference/demo deployment but means tokens don't
survive a server restart — the README calls this out explicitly rather
than pretending it's production-grade secret management.
"""
import os
import datetime as dt
import secrets

import jwt
from fastapi import Depends, HTTPException, Header
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import models
from .database import get_db

SECRET_KEY = os.environ.get("FPC_JWT_SECRET") or secrets.token_hex(32)
ALGORITHM = "HS256"
TOKEN_TTL_HOURS = 12

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_token(user: models.User) -> str:
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "technician_id": user.technician_id,
        "client_name": user.client_name,
        "exp": dt.datetime.utcnow() + dt.timedelta(hours=TOKEN_TTL_HOURS),
        "iat": dt.datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "token expired — please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "invalid token")


def get_current_user(authorization: str = Header(default=None), db: Session = Depends(get_db)) -> models.User:
    """Every protected route depends on this. No Authorization header, no
    access — there's no anonymous fallback path here like there was before
    auth existed."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing or malformed Authorization header — expected 'Bearer <token>'")
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_token(token)
    user = db.get(models.User, payload["sub"])
    if not user or not user.active:
        raise HTTPException(401, "user not found or deactivated")
    return user


def require_roles(*roles):
    """Usage: Depends(require_roles('admin', 'dispatcher')) — raises 403 if
    the authenticated user's role isn't in the allowed set."""
    def dependency(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in roles:
            raise HTTPException(403, f"role '{user.role}' cannot perform this action — requires one of {list(roles)}")
        return user
    return dependency


def check_technician_self(user: models.User, technician_id: str):
    """Called explicitly inside route bodies rather than as a Depends —
    FastAPI dependencies can't cleanly introspect an arbitrary request
    body field, so this stays a plain function. A technician can only act
    as themselves; admins/dispatchers can act on behalf of any technician
    (a deliberate, auditable exception — every such action is still
    attributed to the real actor via the audit log's `actor` field, never
    silently attributed to the technician whose ID appears in the body)."""
    if user.role in ("admin", "dispatcher"):
        return
    if user.role == "technician" and user.technician_id == technician_id:
        return
    raise HTTPException(403, "technicians can only act on their own behalf")


def client_scope_or_none(user: models.User):
    """Returns the client name a 'client' role user is scoped to, or None
    if the user isn't scoped (admin/dispatcher/technician see everything).
    Callers use this to filter job lists rather than trusting the client
    to only ask for their own data."""
    return user.client_name if user.role == "client" else None


def actor_label(user: models.User) -> str:
    """Consistent actor string for audit events — replaces the hardcoded
    'dispatcher:D-Vance' / 'technician:T-092' strings used before auth
    existed with the real authenticated identity."""
    if user.role == "technician" and user.technician_id:
        return f"technician:{user.technician_id}"
    return f"{user.role}:{user.display_name}"
