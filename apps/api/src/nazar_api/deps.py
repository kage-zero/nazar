"""Request-scoped dependencies: settings, DB session, authenticated user."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from nazar_api.models import User
from nazar_api.security import SESSION_COOKIE, user_for_token
from nazar_api.settings import Settings


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_db(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DbDep = Annotated[Session, Depends(get_db)]


def current_user(request: Request, db: DbDep) -> User:
    user = user_for_token(db, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    return user


UserDep = Annotated[User, Depends(current_user)]
