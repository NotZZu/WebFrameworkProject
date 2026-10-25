"""공격(결함 탐색) 시험 — 동시성. 여러 요청이 같은 순간에 들어와도 규칙이 지켜지는가.

파일 DB(SQLite)와 스레드를 써서 실제 서버처럼 요청을 겹쳐 보낸다. 모든 요청은 Barrier 로 같은 순간에 출발시킨다.
"""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from app import create_app
from app.models import CavpApplication, User
from tests import factories
from tests.case_registry import case

PW = factories.DEFAULT_PASSWORD


@pytest.fixture()
def papp(tmp_path):
    """운영과 같은 조건(파일 DB, 처리되지 않은 예외는 500 응답)의 앱."""
    a = create_app({"TESTING": True, "SECRET_KEY": "t" * 32, "DATABASE_URL": f"sqlite:///{tmp_path}/race.db",
                    "CERT_STORAGE_DIR": str(tmp_path)})
    a.config["PROPAGATE_EXCEPTIONS"] = False
    a.testing = False
    return a


def fire(n, job):
    """n 개의 job(i) 를 같은 순간에 시작하고 결과 목록을 돌려준다."""
    barrier = threading.Barrier(n)

    def run(i):
        barrier.wait()
        return job(i)

    with ThreadPoolExecutor(n) as ex:
        return list(ex.map(run, range(n)))


def logged_in(app, user_type="individual", username=None):
    s = app.session_factory()
    u = factories.make_user(s, username=username, user_type=user_type)
    s.close()
    c = app.test_client()
    assert c.post("/api/auth/login", json={"username": u.username, "password": PW}).status_code == 200
    return c, u


@case("IT-ATK-21", "FR-03", "같은 사용자가 같은 알고리즘을 16개 요청으로 동시에 신청",
      "201 은 정확히 1건, 나머지 409, 서버 오류 없음, 신청 1건만 저장", "boundary")
def test_concurrent_duplicate_application(papp):
    c0, u = logged_in(papp)
    session_cookie = c0.get_cookie("session").value

    def job(_):
        c = papp.test_client()
        c.set_cookie("session", session_cookie)
        return c.post("/api/cavp/applications", json={"algorithm_type": "AES"}).status_code

    codes = fire(16, job)
    s = papp.session_factory()
    stored = s.scalar(select(func.count()).select_from(CavpApplication))
    assert all(code in (201, 409) for code in codes), codes
    assert codes.count(201) == 1 and stored == 1, (codes, stored)


@case("IT-ATK-22", "FR-03", "기관 사용자 둘이 같은 심사중 신청을 동시에 승인/반려(각 6건씩, 5라운드 반복)",
      "라운드마다 200 은 정확히 1건, 나머지 409(INVALID_TRANSITION), 최종 상태는 이긴 요청의 값, 서버 오류 없음", "boundary")
def test_concurrent_approve_and_reject(papp):
    s = papp.session_factory()
    person = factories.make_user(s, username="person01")
    factories.make_user(s, username="officer01", user_type="institution")
    apps = [factories.make_application(s, person, "AES", "reviewing").id for _ in range(5)]
    s.close()
    c0 = papp.test_client()
    assert c0.post("/api/auth/login", json={"username": "officer01", "password": PW}).status_code == 200
    cookie = c0.get_cookie("session").value

    for app_id in apps:
        def job(i, app_id=app_id):
            c = papp.test_client()
            c.set_cookie("session", cookie)
            target = "approved" if i % 2 == 0 else "rejected"
            return target, c.patch(f"/api/cavp/applications/{app_id}/status", json={"status": target}).status_code

        results = fire(12, job)
        codes = [code for _, code in results]
        assert all(code in (200, 409) for code in codes), codes
        winners = [t for t, code in results if code == 200]
        s = papp.session_factory()
        final = s.get(CavpApplication, app_id).status
        s.close()
        assert len(winners) == 1 and final == winners[0], (results, final)


@case("IT-ATK-23", "FR-03", "한 사용자가 서로 다른 알고리즘 7종을 동시에 신청", "7건 모두 201, 서버 오류(DB 잠김 등) 없음, 7건 저장", "boundary")
def test_concurrent_different_algorithms(papp):
    from app.services.cavp_service import ALGORITHMS
    c0, _ = logged_in(papp)
    cookie = c0.get_cookie("session").value

    def job(i):
        c = papp.test_client()
        c.set_cookie("session", cookie)
        return c.post("/api/cavp/applications", json={"algorithm_type": ALGORITHMS[i]}).status_code

    codes = fire(len(ALGORITHMS), job)
    s = papp.session_factory()
    assert codes == [201] * len(ALGORITHMS), codes
    assert s.scalar(select(func.count()).select_from(CavpApplication)) == len(ALGORITHMS)


@case("IT-ATK-24", "FR-01", "같은 계정에 틀린 비밀번호를 24개 요청으로 동시에 시도",
      "로그인 시도 제한(5회)이 동시 요청에도 적용되어, 실제로 비밀번호를 검사하는 요청은 5건 이하", "security")
def test_concurrent_brute_force_is_throttled(papp):
    s = papp.session_factory()
    factories.make_user(s, username="victim01")
    s.close()

    def job(i):
        return papp.test_client().post("/api/auth/login", json={"username": "victim01", "password": f"Wrong{i}pass1"}).status_code

    codes = fire(24, job)
    assert all(code in (401, 429) for code in codes), codes
    assert codes.count(401) <= 5, codes
