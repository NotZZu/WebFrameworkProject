"""DB 부하 대응 설정: 파일 SQLite 는 WAL·busy_timeout, 조회용 보조 색인."""
from app.db import init_db, make_engine


def _pragma(engine, name):
    with engine.connect() as c:
        return c.exec_driver_sql(f"PRAGMA {name}").scalar()


def test_파일_SQLite는_WAL과_대기시간이_설정된다(tmp_path):
    e = make_engine(f"sqlite:///{tmp_path / 'a.db'}")
    assert str(_pragma(e, "journal_mode")).lower() == "wal"
    assert int(_pragma(e, "busy_timeout")) >= 5000
    assert int(_pragma(e, "foreign_keys")) == 1


def test_메모리_SQLite는_기존_동작_유지():
    e = make_engine("sqlite://")
    assert int(_pragma(e, "foreign_keys")) == 1


def test_조회용_색인이_만들어진다(tmp_path):
    e = make_engine(f"sqlite:///{tmp_path / 'b.db'}")
    init_db(e)
    with e.connect() as c:
        names = {r[0] for r in c.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"ix_cavp_user_submitted", "ix_cavp_status", "ix_cavp_submitted", "ix_cert_tamper"} <= names
