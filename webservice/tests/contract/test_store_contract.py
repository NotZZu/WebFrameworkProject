"""저장소 계약 시험 — 서비스가 기대하는 동작을 저장소 구현마다 똑같이 지키는지 확인한다."""
import threading
from datetime import datetime

import pytest

from app.errors import DuplicateApplicationError, DuplicateUsernameError

H = "x" * 60


def _user(store, name="alice01", user_type="individual", org=None):
    return store.add_user(name, H, user_type, org)


# ---- 사용자 ----
def test_사용자_저장_후_id와_아이디로_조회된다(store):
    u = _user(store)
    assert isinstance(u.id, int) and u.id > 0
    assert store.get_user(u.id).username == "alice01"
    got = store.get_user_by_username("alice01")
    assert (got.id, got.user_type, got.org_code, got.password_hash) == (u.id, "individual", None, H)
    assert isinstance(got.created_at, datetime)


def test_없는_사용자는_None(store):
    assert store.get_user(9999) is None
    assert store.get_user_by_username("nobody") is None


def test_아이디는_대소문자를_구분한다(store):
    _user(store, "Alice01")
    assert store.get_user_by_username("alice01") is None


def test_같은_아이디_두_번_저장하면_중복_오류(store):
    _user(store)
    with pytest.raises(DuplicateUsernameError):
        _user(store)


def test_같은_아이디_동시_저장은_한_건만_성공한다(new_store):
    ok, dup = [], []

    def run():
        s = new_store()
        try:
            s.add_user("racer01", H, "individual", None)
            ok.append(1)
        except DuplicateUsernameError:
            dup.append(1)
        finally:
            s.close()
    ts = [threading.Thread(target=run) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert (len(ok), len(dup)) == (1, 7)


def test_여러_id로_사용자_조회(store):
    a, b = _user(store, "aaaa01"), _user(store, "bbbb01")
    assert {k: v.username for k, v in store.get_users_by_ids({a.id, b.id, 9999}).items()} == \
        {a.id: "aaaa01", b.id: "bbbb01"}
    assert store.get_users_by_ids([]) == {}


# ---- 세션 ----
def test_세션_저장_조회_삭제(store):
    u = _user(store)
    store.add_session("sid-1", u.id)
    s = store.get_session("sid-1")
    assert (s.sid, s.user_id) == ("sid-1", u.id)
    store.delete_session("sid-1")
    assert store.get_session("sid-1") is None
    store.delete_session("sid-1")  # 없어도 오류 없음


# ---- 시험 신청 ----
def test_신청_저장은_submitted_상태로_시작한다(store):
    u = _user(store)
    a = store.create_application(u.id, "AES")
    got = store.get_application(a.id)
    assert (got.user_id, got.algorithm_type, got.status) == (u.id, "AES", "submitted")
    assert isinstance(got.submitted_at, datetime) and isinstance(got.updated_at, datetime)


def test_진행_중인_같은_알고리즘_신청은_중복_오류(store):
    u = _user(store)
    store.create_application(u.id, "AES")
    with pytest.raises(DuplicateApplicationError):
        store.create_application(u.id, "AES")
    store.create_application(u.id, "RSA")  # 다른 알고리즘은 가능


def test_끝난_신청_뒤에는_같은_알고리즘을_다시_신청할_수_있다(store):
    u = _user(store)
    a = store.create_application(u.id, "AES")
    assert store.change_application_status(a.id, "submitted", "reviewing")
    with pytest.raises(DuplicateApplicationError):
        store.create_application(u.id, "AES")  # 심사 중에도 진행 중
    assert store.change_application_status(a.id, "reviewing", "rejected")
    store.create_application(u.id, "AES")


def test_다른_사용자는_같은_알고리즘을_신청할_수_있다(store):
    a, b = _user(store, "aaaa01"), _user(store, "bbbb01")
    store.create_application(a.id, "AES")
    store.create_application(b.id, "AES")


def test_같은_신청_동시_저장은_한_건만_성공한다(new_store):
    s0 = new_store(); u = _user(s0); s0.close()
    ok, dup = [], []

    def run():
        s = new_store()
        try:
            s.create_application(u.id, "AES")
            ok.append(1)
        except DuplicateApplicationError:
            dup.append(1)
        finally:
            s.close()
    ts = [threading.Thread(target=run) for _ in range(12)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert (len(ok), len(dup)) == (1, 11)
    s1 = new_store()
    assert len(s1.all_applications(u.id)) == 1
    s1.close()


def test_상태_변경은_예상한_상태일_때만_성공한다(store):
    u = _user(store)
    a = store.create_application(u.id, "AES")
    before = store.get_application(a.id).updated_at
    assert store.change_application_status(a.id, "submitted", "reviewing") is True
    got = store.get_application(a.id)
    assert got.status == "reviewing" and got.updated_at >= before
    assert store.change_application_status(a.id, "submitted", "approved") is False  # 예상 상태가 틀림
    assert store.get_application(a.id).status == "reviewing"
    assert store.change_application_status(9999, "submitted", "reviewing") is False


def test_상태_동시_변경은_한_요청만_성공한다(new_store):
    s0 = new_store(); u = _user(s0); a = s0.create_application(u.id, "AES")
    s0.change_application_status(a.id, "submitted", "reviewing"); s0.close()
    results, targets = [], ["approved", "rejected"] * 6

    def run(target):
        s = new_store()
        results.append(s.change_application_status(a.id, "reviewing", target))
        s.close()
    ts = [threading.Thread(target=run, args=(t,)) for t in targets]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count(True) == 1
    s1 = new_store()
    assert s1.get_application(a.id).status in ("approved", "rejected")
    s1.close()


def test_목록은_최신순이고_쪽수와_상태_필터를_지킨다(store):
    u, v = _user(store, "aaaa01"), _user(store, "bbbb01")
    ids = [store.create_application(u.id, alg).id for alg in ("AES", "RSA", "HMAC", "DRBG", "SHA-2")]
    store.create_application(v.id, "AES")
    items, total = store.list_applications(u.id, None, 1, 2)
    assert total == 5 and len(items) == 2
    items_all, total_all = store.list_applications(u.id, None, 1, 10)
    assert [i.id for i in items_all] == sorted(ids, reverse=True)
    page3, _ = store.list_applications(u.id, None, 3, 2)
    assert [i.id for i in page3] == [ids[0]]
    store.change_application_status(ids[0], "submitted", "reviewing")
    only, t = store.list_applications(u.id, "reviewing", 1, 10)
    assert t == 1 and only[0].id == ids[0]
    everyone, total_e = store.list_applications(None, None, 1, 50)
    assert total_e == 6


def test_전체_신청_목록(store):
    u, v = _user(store, "aaaa01"), _user(store, "bbbb01")
    store.create_application(u.id, "AES"); store.create_application(v.id, "AES")
    assert len(store.all_applications(None)) == 2
    assert len(store.all_applications(u.id)) == 1


# ---- 검증서·가명정보(아직 데이터가 없는 경우) ----
def test_검증서와_가명정보가_없으면_빈_결과(store):
    u = _user(store)
    assert store.list_certificates(u.id) == [] and store.list_certificates(None) == []
    assert store.get_personal_info(u.id) is None
