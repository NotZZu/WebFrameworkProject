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
    in_memory = url in ("sqlite://", "sqlite:///:memory:")
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
            if not in_memory:  # 파일 DB: 읽기와 쓰기가 서로 막지 않게(WAL), 잠겼을 때 바로 실패하지 않고 기다린다
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
                dbapi_conn.execute("PRAGMA synchronous=NORMAL")
                dbapi_conn.execute("PRAGMA busy_timeout=10000")
    return engine


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine):
    from . import models  # noqa: F401  (테이블 등록)
    Base.metadata.create_all(engine)
    # 조회용 보조 색인: 목록(사용자별·최신순)·집계(상태별)·최근 N건·위변조 의심 건 찾기가 전체 훑기 없이 끝나도록 한다
    with engine.begin() as conn:
        for ddl in () if engine.dialect.name not in ("sqlite", "postgresql") else (
            "CREATE INDEX IF NOT EXISTS ix_cavp_user_submitted ON cavp_applications (user_id, submitted_at)",
            "CREATE INDEX IF NOT EXISTS ix_cavp_status ON cavp_applications (status)",
            "CREATE INDEX IF NOT EXISTS ix_cavp_submitted ON cavp_applications (submitted_at)",
            "CREATE INDEX IF NOT EXISTS ix_cert_tamper ON certificates (tamper_status)",
        ):
            conn.exec_driver_sql(ddl)
    if engine.dialect.name == "sqlite":
        # 진행 중(접수/심사중)인 같은 사용자·같은 알고리즘 신청은 DB 가 직접 한 건만 허용한다(DF-13).
        # 이미 중복 데이터가 있어 만들 수 없으면 건너뛴다(서비스 계층 검사는 그대로 동작).
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_cavp_active_per_user_algo "
                    "ON cavp_applications (user_id, algorithm_type) WHERE status IN ('submitted','reviewing')")
        except Exception:  # noqa: BLE001
            pass
