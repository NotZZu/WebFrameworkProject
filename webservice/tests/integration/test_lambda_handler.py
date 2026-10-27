"""Lambda 함수 URL 이벤트(payload 2.0) → Flask 변환 시험. 실제 AWS 없이 이벤트를 흉내 내어 확인한다."""
import base64
import json

import boto3
import pytest
from moto import mock_aws

import lambda_handler as lh
from app.store.dynamo import table_spec
from tests.contract.conftest import REGION, serialize_moto

PW = "Passw0rd1"


@pytest.fixture()
def env(monkeypatch):
    serialize_moto(monkeypatch)
    for k, v in (("AWS_ACCESS_KEY_ID", "testing"), ("AWS_SECRET_ACCESS_KEY", "testing"),
                 ("AWS_DEFAULT_REGION", REGION), ("DYNAMODB_TABLE", "svc"), ("SECRET_KEY", "lambda-test-secret"),
                 ("PSEUDONYM_SECRET", "lambda-test-pseudonym")):
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("STORE_BACKEND", raising=False)
    monkeypatch.delenv("ORIGIN_VERIFY", raising=False)
    monkeypatch.setattr(lh, "_app", None)
    with mock_aws():
        boto3.client("dynamodb", region_name=REGION).create_table(**table_spec("svc"))
        yield monkeypatch


def event(method, path, body=None, cookies=None, headers=None, query="", b64=False):
    h = {"host": "d111.cloudfront.net", "x-forwarded-proto": "https"}
    if body is not None:
        h["content-type"] = "application/json"
    h.update(headers or {})
    raw = json.dumps(body) if body is not None else None
    if raw is not None and b64:
        raw = base64.b64encode(raw.encode()).decode()
    return {"version": "2.0", "rawPath": path, "rawQueryString": query, "headers": h, "cookies": cookies or [],
            "requestContext": {"http": {"method": method, "path": path, "sourceIp": "1.2.3.4"}},
            "body": raw, "isBase64Encoded": b64}


def cookie_of(res):
    return [c.split(";")[0] for c in res.get("cookies", [])]


def test_상태점검과_콜드스타트_재사용(env):
    r = lh.handler(event("GET", "/healthz"))
    assert r["statusCode"] == 200
    first = lh._app
    lh.handler(event("GET", "/healthz"))
    assert lh._app is first


def test_가입_로그인_쿠키로_내정보_조회(env):
    body = {"username": "lam_user01", "password": PW, "user_type": "individual"}
    assert lh.handler(event("POST", "/api/auth/signup", body))["statusCode"] == 201
    res = lh.handler(event("POST", "/api/auth/login", {"username": "lam_user01", "password": PW}, b64=True))
    assert res["statusCode"] == 200
    assert any("Secure" in c and "HttpOnly" in c for c in res["cookies"])
    me = lh.handler(event("GET", "/api/auth/me", cookies=cookie_of(res)))
    assert me["statusCode"] == 200 and json.loads(me["body"])["username"] == "lam_user01"
    assert lh.handler(event("GET", "/api/auth/me"))["statusCode"] == 401


def test_로그아웃한_쿠키는_다시_쓸_수_없다(env):
    lh.handler(event("POST", "/api/auth/signup", {"username": "lam_user02", "password": PW, "user_type": "individual"}))
    login = lh.handler(event("POST", "/api/auth/login", {"username": "lam_user02", "password": PW}))
    old = cookie_of(login)
    lh.handler(event("POST", "/api/auth/logout", {}, cookies=old))
    assert lh.handler(event("GET", "/api/auth/me", cookies=old))["statusCode"] == 401


def test_쿼리스트링과_html_본문(env):
    r = lh.handler(event("GET", "/", query="a=1"))
    assert r["statusCode"] in (200, 302) and "isBase64Encoded" not in r


def test_바이너리_응답은_base64(env):
    app = lh._get_app()

    @app.get("/_bin")
    def _bin():
        return b"\x00\xff\x10", 200, {"Content-Type": "application/octet-stream"}
    r = lh.handler(event("GET", "/_bin"))
    assert r["isBase64Encoded"] and base64.b64decode(r["body"]) == b"\x00\xff\x10"


def test_같은_이름의_헤더와_여러_쿠키(env):
    app = lh._get_app()

    @app.get("/_multi")
    def _multi():
        from flask import make_response
        r = make_response("ok")
        r.headers.add("X-A", "1")
        r.headers.add("X-A", "2")
        r.set_cookie("a", "1")
        r.set_cookie("b", "2")
        return r
    r = lh.handler(event("GET", "/_multi"))
    assert r["headers"]["x-a"] == "1,2" and len(r["cookies"]) == 2


def test_원본_확인_헤더가_설정되면_직접_호출은_거부(env):
    env.setenv("ORIGIN_VERIFY", "s3cret-value")
    assert lh.handler(event("GET", "/healthz"))["statusCode"] == 403
    assert lh.handler(event("GET", "/healthz", headers={"x-origin-verify": "wrong"}))["statusCode"] == 403
    assert lh.handler(event("GET", "/healthz", headers={"x-origin-verify": "s3cret-value"}))["statusCode"] == 200


def test_설정_오류는_상세를_숨기고_500(env):
    env.delenv("SECRET_KEY")
    r = lh.handler(event("GET", "/healthz"))
    assert r["statusCode"] == 500 and "SECRET_KEY" not in r["body"]
