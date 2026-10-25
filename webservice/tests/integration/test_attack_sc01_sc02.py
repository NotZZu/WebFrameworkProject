"""공격(결함 탐색) 시험 — SC-01 인증 / SC-02 대시보드.

일반 시험이 "명세대로 동작하는가"를 확인한다면, 이 파일은 "깨뜨릴 수 있는가"를 확인한다.
각 시험은 '안전하게 동작해야 하는 쪽'을 단언한다. 따라서 실패하면 곧 결함(DF-xx)이다.
발견된 결함의 시험은 tests/red_cases.txt 에 올려 두고(xfail), 고치면 목록에서 지운다.
결함 상세는 docs/defect-log.md 참고.
"""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from app import create_app
from app.models import User
from tests import factories
from tests.case_registry import case
from tests.integration.conftest import login

PW = factories.DEFAULT_PASSWORD


def signup(client, **over):
    body = {"username": "attacker01", "password": PW, "user_type": "individual"}
    body.update(over)
    return client.post("/api/auth/signup", json=body)


def n_users(db):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(User))


@pytest.fixture()
def prod_client(app):
    """운영과 같은 조건: 처리되지 않은 예외는 전파되지 않고 500 응답이 된다."""
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.testing = False
    return app.test_client()


# ───────── 비밀번호·아이디 입력 공격 ─────────

@case("IT-ATK-01", "FR-01", "최대 길이(64자) 비밀번호에서 마지막 글자만 다른 비밀번호로 로그인",
      "다른 비밀번호는 로그인 실패(401), 원래 비밀번호는 성공", "boundary")
def test_max_length_password_last_char_matters(client):
    base = "A1" + "x" * 61
    assert signup(client, password=base + "a").status_code == 201
    assert login(client, "attacker01", base + "b").status_code == 401
    assert login(client, "attacker01", base + "a").status_code == 200


@case("IT-ATK-02", "FR-01", "한글 비밀번호의 바이트 한도(글자 수는 64자 이내지만 바이트는 72 초과)",
      "잘려서 같은 비밀번호로 취급되지 않는다(가입 거부 또는 로그인 401)", "security")
def test_multibyte_password_not_truncated(client):
    base = "가" * 30  # 90바이트
    r = signup(client, password=base + "a1끝1")
    if r.status_code == 400:
        return
    assert r.status_code == 201
    assert login(client, "attacker01", base + "a1끝2").status_code == 401


@case("IT-ATK-03", "FR-01", "NUL 문자(\\x00)가 든 비밀번호로 가입/로그인",
      "서버 오류(500) 없이 가입 400, 로그인 401", "negative")
def test_nul_in_password_no_server_error(prod_client):
    r = signup(prod_client, password="Passw0rd1\x00tail")
    assert r.status_code == 400
    r2 = login(prod_client, "someone", "Passw0rd1\x00tail")
    assert r2.status_code == 401


@case("IT-ATK-04", "FR-01", "유니코드 숫자(아라비아-인도 숫자 등)만으로 '숫자 1자 이상' 규칙 통과 시도",
      "ASCII 숫자가 없으면 400", "boundary")
def test_unicode_digit_does_not_satisfy_digit_rule(client, db):
    r = signup(client, password="abcdefgh٣")  # ٣
    assert r.status_code == 400
    assert n_users(db) == 0


@pytest.mark.parametrize("name", ["alice01\n", " alice01", "alice01 ", "ａｌｉｃｅ０１", "al​ice01", "a" * 21, "abc"])
@case("IT-ATK-05", "FR-01", "아이디 변형 입력: 줄바꿈·공백·전각 문자·제로폭 문자·길이 초과/미달",
      "모두 400, 사용자 생성 없음", "boundary")
def test_username_variants_rejected(client, db, name):
    assert signup(client, username=name).status_code == 400
    assert n_users(db) == 0


@case("IT-ATK-06", "FR-01", "기관 코드에 비정상적으로 긴 문자열(1만 자)과 제어 문자",
      "설계서 VARCHAR(50) 한도를 넘으면 400, 사용자 생성 없음", "boundary")
def test_org_code_length_and_control_chars(client, db):
    assert signup(client, user_type="company", org_code="O" * 10_000).status_code == 400
    assert signup(client, username="attacker02", user_type="company", org_code="ORG\x00\x1b[31m").status_code == 400
    assert n_users(db) == 0


@case("IT-ATK-07", "FR-01", "SQL 인젝션 문자열을 아이디/비밀번호에 입력",
      "가입 400, 로그인 401, users 테이블 변화 없음", "security")
def test_sql_injection_in_credentials(client, db):
    factories.make_user(db, username="victim01")
    before = n_users(db)
    for evil in ("' OR '1'='1", "victim01'--", "x'; DROP TABLE users;--"):
        assert signup(client, username=evil).status_code == 400
        assert login(client, evil, "' OR '1'='1").status_code == 401
    assert login(client, "victim01", "' OR '1'='1").status_code == 401
    assert n_users(db) == before


@pytest.mark.parametrize("field,value", [
    ("username", ["a"]), ("username", {"a": 1}), ("username", 12345678), ("username", None),
    ("password", ["x"]), ("password", {"x": 1}), ("password", 12345678), ("password", None),
    ("user_type", ["individual"]), ("user_type", {"t": 1}), ("org_code", ["x"]), ("org_code", {"x": 1}),
])
@case("IT-ATK-08", "FR-01", "필드 타입 혼동(문자열 자리에 배열·객체·숫자·null)",
      "서버 오류 없이 가입 400 / 로그인 401", "negative")
def test_type_confusion_never_500(prod_client, field, value):
    body = {"username": "attacker01", "password": PW, "user_type": "company", "org_code": "ORG-1"}
    body[field] = value
    assert prod_client.post("/api/auth/signup", json=body).status_code == 400
    lb = {"username": "attacker01", "password": PW}
    if field in lb:
        lb[field] = value
        assert prod_client.post("/api/auth/login", json=lb).status_code == 401


# ───────── 요청 형식·크기 공격 ─────────

@case("IT-ATK-09", "FR-01", "깊게 중첩된 JSON 본문(10만 단계)", "서버 오류(500) 없이 400", "negative")
def test_deeply_nested_json(prod_client):
    r = prod_client.post("/api/auth/login", data="[" * 100_000, content_type="application/json")
    assert r.status_code == 400


@case("IT-ATK-10", "FR-01", "JSON이 아닌 요청(form, 빈 본문, 배열, 문자열)", "모두 400 JSON 오류 형식", "negative")
def test_non_json_bodies(prod_client):
    for kw in (dict(data="username=a&password=b"), dict(data=""), dict(json=[1, 2]), dict(json="text")):
        r = prod_client.post("/api/auth/login", **kw)
        assert r.status_code == 400 and r.get_json()["error"]["code"] == "VALIDATION_ERROR"


@case("IT-ATK-11", "FR-01", "2MB 크기의 요청 본문", "본문 크기 제한으로 413 거부", "boundary")
def test_oversized_body_is_rejected(client):
    r = client.post("/api/auth/login", data=json.dumps({"username": "a" * 2_000_000, "password": "x"}),
                    content_type="application/json")
    assert r.status_code == 413


# ───────── 인증·세션 공격 ─────────

@case("IT-ATK-12", "FR-01", "같은 계정에 비밀번호를 연속으로 틀려 입력(무차별 대입)",
      "일정 횟수 뒤 429 등으로 제한되고, 제한 중에는 올바른 비밀번호도 거부", "security")
def test_brute_force_is_throttled(client, db):
    factories.make_user(db, username="victim01")
    codes = [login(client, "victim01", f"Wrong{i}pass1").status_code for i in range(12)]
    assert 429 in codes
    assert login(client, "victim01").status_code in (423, 429)


@case("IT-ATK-13", "FR-01", "로그아웃 전에 훔친 세션 쿠키를 로그아웃 후 재사용",
      "로그아웃한 세션은 서버에서 무효 → 401", "security")
def test_session_cookie_replay_after_logout(app, db):
    factories.make_user(db, username="victim01")
    c = app.test_client()
    assert login(c, "victim01").status_code == 200
    stolen = c.get_cookie("session").value
    assert c.post("/api/auth/logout").status_code == 204
    thief = app.test_client()
    thief.set_cookie("session", stolen)
    assert thief.get("/api/auth/me").status_code == 401


@case("IT-ATK-14", "FR-01", "기본 비밀키(dev-secret-change-me)로 세션 쿠키 위조",
      "운영 구성에서 기본 키로는 서버가 뜨지 않거나, 위조 쿠키는 거부(401)", "security")
def test_forged_session_with_default_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    try:
        victim_app = create_app({"DATABASE_URL": "sqlite://", "CERT_STORAGE_DIR": str(tmp_path)})
    except RuntimeError:
        return  # 기본 키로는 기동 거부 → 안전
    s = victim_app.session_factory()
    user = factories.make_user(s, username="victim01", user_type="institution")
    forged_app = create_app({"DATABASE_URL": "sqlite://", "SECRET_KEY": "dev-secret-change-me",
                             "CERT_STORAGE_DIR": str(tmp_path)})
    cookie = forged_app.session_interface.get_signing_serializer(forged_app).dumps({"user_id": user.id})
    c = victim_app.test_client()
    c.set_cookie("session", cookie)
    assert c.get("/api/auth/me").status_code == 401


@case("IT-ATK-15", "FR-01", "응답 보안 헤더(nosniff, 프레임 삽입 차단)", "X-Content-Type-Options: nosniff, X-Frame-Options 또는 CSP frame-ancestors", "security")
def test_security_headers(client):
    r = client.get("/")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    csp = r.headers.get("Content-Security-Policy", "")
    assert r.headers.get("X-Frame-Options") in ("DENY", "SAMEORIGIN") or "frame-ancestors" in csp


@case("IT-ATK-16", "FR-01", "세션 쿠키 속성: HttpOnly·SameSite·Secure", "운영 설정에서 세 속성이 모두 켜짐", "security")
def test_session_cookie_flags(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    a = create_app({"DATABASE_URL": "sqlite://", "CERT_STORAGE_DIR": str(tmp_path)})
    assert a.config["SESSION_COOKIE_HTTPONLY"] is True
    assert a.config["SESSION_COOKIE_SAMESITE"] in ("Lax", "Strict")
    assert a.config["SESSION_COOKIE_SECURE"] is True


@case("IT-ATK-17", "FR-01", "로그인 실패 응답의 계정 존재 여부 은닉", "없는 아이디와 틀린 비밀번호의 응답(상태·본문)이 동일", "security")
def test_login_failure_does_not_reveal_account(client, db):
    factories.make_user(db, username="victim01")
    a = login(client, "victim01", "Wrong1pass")
    b = login(client, "nobody99", "Wrong1pass")
    assert a.status_code == b.status_code == 401 and a.get_json() == b.get_json()


# ───────── SC-02 대시보드 공격 ─────────

@case("IT-ATK-18", "FR-03", "대시보드 요청에 user_id/scope 쿼리를 붙여 타인·전체 범위 요청",
      "쿼리는 무시되고 로그인 사용자 본인 범위만 반환", "security")
def test_dashboard_ignores_user_id_query(login_as, db):
    a_client, a = login_as("individual")
    b = factories.make_user(db, username="victim02")
    factories.make_application(db, b)
    base = a_client.get("/api/dashboard").get_json()
    probe = a_client.get(f"/api/dashboard?user_id={b.id}&scope=all&role=institution").get_json()
    assert probe == base and probe["scope"] != "all"


@case("IT-ATK-19", "FR-03", "대시보드 접근에 변조된 세션(존재하지 않는 user_id)", "401 이고 세션이 정리됨", "security")
def test_dashboard_with_deleted_user_session(login_as, db):
    c, u = login_as("individual")
    db.delete(db.get(User, u.id))
    db.commit()
    assert c.get("/api/dashboard").status_code == 401
    assert c.get("/api/auth/me").status_code == 401


# ───────── 동시성 ─────────

@case("IT-ATK-20", "FR-01", "같은 아이디로 12개 요청을 동시에 가입", "정확히 1건 201, 나머지 409, 서버 오류(500) 없음, users 1건", "boundary")
def test_concurrent_signup_same_username(tmp_path):
    a = create_app({"TESTING": True, "SECRET_KEY": "t" * 32, "DATABASE_URL": f"sqlite:///{tmp_path}/race.db",
                    "CERT_STORAGE_DIR": str(tmp_path)})
    a.config["PROPAGATE_EXCEPTIONS"] = False
    a.testing = False

    def go(_):
        return a.test_client().post("/api/auth/signup", json={"username": "racer01", "password": PW,
                                                               "user_type": "individual"}).status_code

    with ThreadPoolExecutor(12) as ex:
        codes = list(ex.map(go, range(12)))
    assert codes.count(201) == 1 and all(c in (201, 409) for c in codes), codes
    s = a.session_factory()
    assert s.scalar(select(func.count()).select_from(User)) == 1
