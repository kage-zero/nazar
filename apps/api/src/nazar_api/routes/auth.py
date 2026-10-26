"""Operator accounts: first-run setup, sign in, sign out, current state."""

import ipaddress

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select

from nazar_api.deps import DbDep, SettingsDep
from nazar_api.models import User
from nazar_api.security import (
    SESSION_COOKIE,
    create_session,
    end_session,
    hash_password,
    user_for_token,
    verify_password,
)
from nazar_api.settings import Settings
from nazar_contracts import AuthState, Credentials, UserPublic

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public(user: User) -> UserPublic:
    return UserPublic(id=user.id, email=user.email)


def _set_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        path="/",
    )


def _is_loopback(request: Request) -> bool:
    host = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in {"localhost", "testclient"}


@router.get("/state", response_model=AuthState)
def auth_state(request: Request, db: DbDep) -> AuthState:
    users = db.scalar(select(func.count()).select_from(User)) or 0
    user = user_for_token(db, request.cookies.get(SESSION_COOKIE))
    return AuthState(setup_required=users == 0, user=_public(user) if user else None)


@router.post("/setup", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def first_run_setup(
    body: Credentials, request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> UserPublic:
    """Create the first operator account. Allowed only while no account exists, only from
    this machine, and never in production (use NAZAR_BOOTSTRAP_ADMIN_* there)."""
    if settings.env == "production" or not _is_loopback(request):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "First-run setup is only available on this machine."
        )
    if db.scalar(select(func.count()).select_from(User)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An operator account already exists.")
    user = User(email=body.email.lower(), password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    _set_cookie(response, create_session(db, user, settings.session_days), settings)
    return _public(user)


@router.post("/login", response_model=UserPublic)
def login(
    body: Credentials, request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> UserPublic:
    throttle = request.app.state.login_throttle
    key = f"{request.client.host if request.client else '?'}|{body.email.lower()}"
    if throttle.blocked(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again later."
        )
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        throttle.fail(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect.")
    throttle.reset(key)
    _set_cookie(response, create_session(db, user, settings.session_days), settings)
    return _public(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbDep, settings: SettingsDep) -> None:
    end_session(db, request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/", secure=settings.secure_cookies)
