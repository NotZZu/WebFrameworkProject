"""통합시험 IT — FR-01 인증 API ↔ users 테이블 / 세션."""
import pytest
from sqlalchemy import func, select

from app.models import User
from tests import factories
from tests.case_registry import case
from tests.integration.conftest import login

PW = factories.DEFAULT_PASSWORD


def signup(client, **over):
    body = {"username": "alice01", "password": PW, "user_type": "individual"}
    body.update(over)
    return client.post("/api/auth/signup", json=body)


def n_users(db):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(User))


@case("IT-01", "FR-01", "POST /api/auth/signup: 동일 아이디 2회 요청", "1차 201, 2차 409(DUPLICATE_USERNAME), users 1건")
def test_signup_duplicate(client, db):
    assert signup(client).status_code == 201
    r = signup(client)
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "DUPLICATE_USERNAME"
    assert n_users(db) == 1


@case("IT-02", "FR-01", "POST /api/auth/signup: 정상 가입 응답", "201, 응답에 id/username/user_type, 비밀번호·해시 미포함, DB 에는 bcrypt 해시")
def test_signup_response_and_storage(client, db):
    r = signup(client, user_type="company", org_code="ORG-9")
    body = r.get_json()
    assert r.status_code == 201 and body["username"] == "alice01" and body["user_type"] == "company" and "id" in body
    assert "password" not in body and "password_hash" not in body
    db.expire_all()
    assert db.scalar(select(User)).password_hash.startswith("$2")


@case("IT-03", "FR-01", "POST /api/auth/signup: 잘못된 입력", "400 VALIDATION_ERROR, users 0건", "negative")
@pytest.mark.parametrize("over", [
    {"username": "ab"}, {"password": "short1"}, {"password": "12345678"}, {"user_type": "admin"},
    {"user_type": "company"}, {"username": "bad name"}, {"username": None},
])
def test_signup_validation(client, db, over):
    r = signup(client, **over)
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert n_users(db) == 0


@case("IT-04", "FR-01", "POST /api/auth/signup: 본문 없음/JSON 아님", "400 (500 이 아님)", "negative")
def test_signup_malformed_body(client):
    assert client.post("/api/auth/signup").status_code == 400
    assert client.post("/api/auth/signup", data="not json", content_type="text/plain").status_code == 400
    assert client.post("/api/auth/signup", data="{broken", content_type="application/json").status_code == 400


@case("IT-05", "FR-01", "POST /api/auth/login: 로그인 후 세션 유지", "200 → GET /api/auth/me 가 본인 정보 반환")
def test_login_then_me(client, db):
    factories.make_user(db, "alice01")
    r = login(client, "alice01")
    assert r.status_code == 200 and r.get_json()["username"] == "alice01"
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.get_json()["username"] == "alice01"


@case("IT-06", "FR-01", "POST /api/auth/login: 세션 쿠키 보안 속성", "Set-Cookie 에 HttpOnly 와 SameSite 포함", "security")
def test_login_cookie_flags(client, db):
    factories.make_user(db, "alice01")
    cookies = login(client, "alice01").headers.getlist("Set-Cookie")
    assert cookies and any("HttpOnly" in c and "SameSite" in c for c in cookies)


@case("IT-07", "FR-01", "POST /api/auth/login: 실패 시 401, 계정 존재 여부 비노출", "없는 아이디/틀린 비밀번호의 응답 본문 동일, 이후에도 /me 는 401", "security")
def test_login_failure_uniform(client, db):
    factories.make_user(db, "alice01")
    r1 = login(client, "ghost01")
    r2 = login(client, "alice01", "Wrong0000")
    assert r1.status_code == r2.status_code == 401
    assert r1.get_json() == r2.get_json() and r1.get_json()["error"]["code"] == "AUTHENTICATION_FAILED"
    assert client.get("/api/auth/me").status_code == 401


@case("IT-08", "FR-01", "POST /api/auth/login: SQL 인젝션/빈 값", "401 또는 400, 500 없음", "security")
@pytest.mark.parametrize("u,p", [("' OR '1'='1", "x"), ("alice01' --", PW), ("", ""), (None, None)])
def test_login_injection(client, db, u, p):
    factories.make_user(db, "alice01")
    r = client.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code in (400, 401)
    assert client.get("/api/auth/me").status_code == 401


@case("IT-09", "FR-01", "POST /api/auth/logout: 세션 종료", "204 이후 /me 401, 재로그아웃도 오류 없음")
def test_logout(client, db):
    factories.make_user(db, "alice01")
    login(client, "alice01")
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/logout").status_code in (204, 401)


@case("IT-10", "FR-01", "세션: 서로 다른 클라이언트 격리 / 위조 쿠키", "A 로그인이 B 에 영향 없음, 임의 쿠키는 401", "security")
def test_session_isolation_and_forged_cookie(make_client, db):
    factories.make_user(db, "alice01")
    a, b = make_client(), make_client()
    login(a, "alice01")
    assert a.get("/api/auth/me").status_code == 200 and b.get("/api/auth/me").status_code == 401
    b.set_cookie("session", "forged.value.here")
    assert b.get("/api/auth/me").status_code == 401


@case("IT-11", "FR-01", "보호 API: 미로그인 호출", "401 반환, 어떤 레코드도 생성되지 않음", "security")
@pytest.mark.parametrize("method,url,body", [
    ("post", "/api/privacy/process", {"mode": "anonymous", "name": "홍길동", "birthdate": "1990-04-12"}),
    ("get", "/api/privacy/me", None),
    ("post", "/api/cavp/applications", {"algorithm_type": "AES"}),
    ("get", "/api/cavp/applications", None),
    ("get", "/api/cavp/applications/1", None),
    ("patch", "/api/cavp/applications/1/status", {"status": "reviewing"}),
    ("post", "/api/cavp/applications/1/certificate", {"cert_type": "CAVP", "content": "x"}),
    ("get", "/api/certificates", None),
    ("get", "/api/certificates/1", None),
    ("get", "/api/certificates/1/verify", None),
])
def test_protected_endpoints_require_login(client, db, method, url, body):
    r = getattr(client, method)(url, **({"json": body} if body is not None else {}))
    assert r.status_code == 401 and r.get_json()["error"]["code"] == "AUTHENTICATION_FAILED"
    from app.models import CavpApplication, PersonalInfo, Certificate
    for m in (CavpApplication, PersonalInfo, Certificate):
        assert db.scalar(select(func.count()).select_from(m)) == 0


@case("IT-12", "FR-01", "오류 응답 형식 일관성", "존재하지 않는 /api 경로 404, 잘못된 메서드 405 모두 JSON {error:{code,message}}", "boundary")
def test_error_shape_is_json(client):
    r404 = client.get("/api/nope")
    r405 = client.put("/api/auth/login")
    for r, code in ((r404, "NOT_FOUND"), (r405, "METHOD_NOT_ALLOWED")):
        assert r.is_json and r.get_json()["error"]["code"] == code and r.get_json()["error"]["message"]
