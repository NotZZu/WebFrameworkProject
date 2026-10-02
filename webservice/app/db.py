"""DB 인프라 (시스템설계서 v1.1 5장 테이블 정의의 스캐폴딩 — 동작 로직 없음)."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    if url in ("sqlite://", "sqlite:///:memory:"):
        engine = create_engine(
            url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    else:
        engine = create_engine(url)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    return engine


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine):
    from . import models  # noqa: F401  (테이블 등록)
    Base.metadata.create_all(engine)
