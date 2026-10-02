"""통합시험 IT — FR-02 가명·익명 처리 API ↔ personal_info 테이블."""
import pytest
from sqlalchemy import func, select, text

from app.models import PersonalInfo
from tests.case_registry import case

BODY = {"mode": "pseudonym", "name": "홍길동", "birthdate": "1990-04-12"}


def dump_all(db):
    out = ""
    for (t,) in db.execute(text("SELECT name FROM sqlite_master WHERE type='table'")):
        out += str(db.execute(text(f"SELECT * FROM {t}")).fetchall())
    return out


@case("IT-13", "FR-02", "POST /api/privacy/process: 가명/익명 각 1회", "level별 personal_info 가 올바른 값으로 저장 (가명=PSN-…, 익명=None/'익명')")
def test_process_both_modes(login_as, db):
    c, u = login_as()
    r = c.post("/api/privacy/process", json=BODY)
    assert r.status_code == 200 and r.get_json()["level"] == "pseudonym" and r.get_json()["pseudonym_id"].startswith("PSN-")
    r = c.post("/api/privacy/process", json={**BODY, "mode": "anonymous"})
    assert r.get_json()["level"] == "anonymous" and r.get_json()["pseudonym_id"] is None
    db.expire_all()
    row = db.scalar(select(PersonalInfo))
    assert db.scalar(select(func.count()).select_from(PersonalInfo)) == 1
    assert row.anonymization_level == "anonymous" and row.masked_display_value == "익명"


@case("IT-14", "FR-02", "가명·익명 처리: 원본 개인정보 비저장·비노출", "응답과 DB 전 테이블 어디에도 '홍길동' / '1990-04-12' 없음", "security")
def test_raw_pii_never_stored_or_returned(login_as, db):
    c, _ = login_as()
    r = c.post("/api/privacy/process", json=BODY)
    assert "홍길동" not in r.get_data(as_text=True) and "1990-04-12" not in r.get_data(as_text=True)
    me = c.get("/api/privacy/me")
    assert me.status_code == 200 and "홍길동" not in me.get_data(as_text=True)
    d = dump_all(db)
    assert "홍길동" not in d and "1990-04-12" not in d


@case("IT-15", "FR-02", "POST /api/privacy/process: 잘못된 입력", "400 VALIDATION_ERROR, personal_info 0건", "negative")
@pytest.mark.parametrize("over", [{"mode": "x"}, {"name": ""}, {"birthdate": "not-a-date"},
                                  {"birthdate": "2999-01-01"}, {"birthdate": "1990-13-40"}, {"name": None}])
def test_process_validation(login_as, db, over):
    c, _ = login_as()
    r = c.post("/api/privacy/process", json={**BODY, **over})
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert db.scalar(select(func.count()).select_from(PersonalInfo)) == 0


@case("IT-16", "FR-02", "GET /api/privacy/me: 처리 전 404, 처리 후 200", "404 NOT_FOUND → 200 {level, display, pseudonym_id}")
def test_get_my_privacy(login_as):
    c, _ = login_as()
    assert c.get("/api/privacy/me").status_code == 404
    c.post("/api/privacy/process", json=BODY)
    body = c.get("/api/privacy/me").get_json()
    assert body["level"] == "pseudonym" and body["display"].startswith("홍*동 (") and body["display"].endswith("대)")


@case("IT-17", "FR-02", "개인정보 처리 결과는 본인 것만 조회", "A 의 처리 결과가 B 의 /privacy/me 에 노출되지 않음", "security")
def test_privacy_isolation(login_as):
    a, _ = login_as(username="usera01")
    b, _ = login_as(username="userb01")
    assert a.post("/api/privacy/process", json=BODY).status_code == 200
    assert a.get("/api/privacy/me").status_code == 200   # 전제: A 본인은 조회 가능(빈 통과 방지)
    assert b.get("/api/privacy/me").status_code == 404
