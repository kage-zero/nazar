"""Database engine and declarative base.

Models (missions, assets, jobs, events, artifacts) arrive in Milestone 2 together with
their first Alembic revision; Stage 1 only proves connectivity.
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)
