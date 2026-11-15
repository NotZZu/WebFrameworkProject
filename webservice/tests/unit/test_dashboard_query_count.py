"""대시보드 쿼리 수 상한 — 데이터가 적은 개인 화면에 집계 질의를 늘리지 않고, 기관 화면은 전체를 읽지 않는다."""
import pytest
from sqlalchemy import event

from app.db import init_db, make_engine, make_session_factory
from app.services import admin_service, dashboard_service
from app.store import SqlStore


@pytest.fixture()
def env(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'q.db'}")
    init_db(engine)
    sf = make_session_factory(engine)
    s = SqlStore(sf())
    inst = s.add_user("inst01", "x" * 60, "institution", "ORG")
    user = s.add_user("u01", "x" * 60, "individual", None)
    for a in ("AES", "RSA", "SHA-2"):
        s.create_application(user.id, a)
    count = {"n": 0, "rows": 0}

    @event.listens_for(engine, "before_cursor_execute")
    def _c(conn, cur, st, params, ctx, many):
        count["n"] += 1
    yield sf, user, inst, count
    s.close()


def _queries(sf, count, fn, uid):
    session = sf()
    count["n"] = 0
    fn(session, uid)
    session.close()
    return count["n"]


def test_개인_대시보드는_쿼리_4개_이하(env):
    sf, user, inst, count = env
    assert _queries(sf, count, dashboard_service.get_summary, user.id) <= 4


def test_기관_대시보드와_관리자_요약은_쿼리_수가_신청_수와_무관하다(env):
    sf, user, inst, count = env
    base_d = _queries(sf, count, dashboard_service.get_summary, inst.id)
    base_a = _queries(sf, count, admin_service.get_summary, inst.id)
    s = SqlStore(sf())
    for i in range(40):
        u = s.add_user(f"x{i:02d}", "x" * 60, "individual", None)
        s.create_application(u.id, "AES")
    s.close()
    assert _queries(sf, count, dashboard_service.get_summary, inst.id) == base_d
    assert _queries(sf, count, admin_service.get_summary, inst.id) == base_a
