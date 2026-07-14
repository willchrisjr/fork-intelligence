from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from fork_intelligence.db import get_session_factory


def get_db_session() -> Generator[Session]:
    with get_session_factory()() as session:
        yield session
