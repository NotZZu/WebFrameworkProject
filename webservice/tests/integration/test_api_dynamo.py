"""서버리스 배포 구성(STORE_BACKEND=dynamodb)으로 API 전체 흐름과 공격 시나리오를 확인한다. DynamoDB 는 moto 로 흉내 낸다."""
import threading

import boto3
import pytest
from moto import mock_aws

from app import create_app
from app.store.dynamo import table_spec
from tests.contract.conftest import REGION, serialize_moto

PW = "Passw0rd1"


@pytest.fixture()
def app(monkeypatch):
    serialize_moto(monkeypatch)
    for k, v in (("AWS_ACCESS_KEY_ID", "testing"), ("AWS_SECRET_ACCESS_KEY", "testing"),
                 ("AWS_DEFAULT_REGION", REGION)):
        monkeypatch.setenv(k, v)
    with mock_aws():
        boto3.client("dynamodb", region_name=REGION).create_table(**table_spec("svc"))
        yield create_app({"TESTING": True, "STORE_BACKEND": "dynamodb", "DYNAMODB_TABLE": "svc",
                          "SECRET_KEY": "test-secret", "PSEUDONYM_SECRET": "test-pseudonym"})


def signup(c, name, user_type="individual", org=None):
    body = {"username": name, "password": PW, "user_type": user_type}
    if org:
        body["org_code"] = org
    return c.post("/api/auth/signup", json=body)


def login(c, name, pw=PW):
    return c.post("/api/auth/login", json={"username": name, "password": pw})


def test_가입_로그인_내정보_로그아웃_흐름(app):
    c = app.test_client()
    assert signup(c, "dyn_user01").status_code == 201
    assert signup(c, "dyn_user01").status_code == 409  # 아이디 중복
    assert c.get("/api/auth/me").status_code == 401
    r = login(c, "dyn_user01")
    assert r.status_code == 200 and r.get_json()["username"] == "dyn_user01"
    assert c.get("/api/auth/me").get_json()["user_type"] == "individual"
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/auth/me").status_code == 401


def test_로그아웃한_쿠키를_다시_써도_거절된다_DF03(app):
    c = app.test_client()
    signup(c, "dyn_user02"); login(c, "dyn_user02")
    stolen = c.get_cookie("session").value
    c.post("/api/auth/logout")
    thief = app.test_client()
    thief.set_cookie("session", stolen)
    assert thief.get("/api/auth/me").status_code == 401


def test_틀린_비밀번호_5회_뒤_차단된다_DF02(app):
    c = app.test_client()
    signup(c, "dyn_user03")
    codes = [login(c, "dyn_user03", "Wr0ngPass1").status_code for _ in range(7)]
    assert codes == [401] * 5 + [429] * 2
    assert login(c, "dyn_user03").status_code == 429  # 올바른 비밀번호도 차단


def test_동시_로그인_시도도_한도를_넘지_못한다_DF15(app):
    signup(app.test_client(), "dyn_user04")
    codes = []

    def run():
        codes.append(login(app.test_client(), "dyn_user04", "Wr0ngPass1").status_code)
    ts = [threading.Thread(target=run) for _ in range(20)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert codes.count(401) == 5 and codes.count(429) == 15


def test_시험_신청_심사_대시보드_흐름(app):
    user, inst = app.test_client(), app.test_client()
    signup(user, "dyn_user05"); login(user, "dyn_user05")
    signup(inst, "dyn_inst05", "institution", "ORG-1"); login(inst, "dyn_inst05")

    r = user.post("/api/cavp/applications", json={"algorithm_type": "AES"})
    assert r.status_code == 201
    app_id = r.get_json()["id"]
    assert user.post("/api/cavp/applications", json={"algorithm_type": "AES"}).status_code == 409
    assert user.post("/api/cavp/applications", json={"algorithm_type": "RSA"}).status_code == 201

    assert user.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "reviewing"}).status_code == 403
    assert inst.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "approved"}).status_code == 409
    assert inst.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "reviewing"}).status_code == 200
    assert inst.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "approved"}).status_code == 200
    assert user.post("/api/cavp/applications", json={"algorithm_type": "AES"}).status_code == 201  # 끝난 뒤 재신청

    mine = user.get("/api/cavp/applications").get_json()
    assert mine["total"] == 3 and mine["scope"] == "own"
    assert [i["algorithm_type"] for i in mine["items"]] == ["AES", "RSA", "AES"]  # 최신순
    assert all(i["owner"] == "dyn_user05" for i in mine["items"])
    everyone = inst.get("/api/cavp/applications").get_json()
    assert everyone["total"] == 3 and everyone["scope"] == "all"
    approved = inst.get("/api/cavp/applications?status=approved").get_json()
    assert approved["total"] == 1 and approved["items"][0]["id"] == app_id
    assert user.get(f"/api/cavp/applications/{app_id}").get_json()["status_label"] == "시험 완료"

    d = user.get("/api/dashboard").get_json()
    assert d["applications"]["total"] == 3 and d["applications"]["by_status"]["approved"] == 1
    assert d["certificates"] == {"total": 0, "suspected": 0}
    assert d["privacy"] == {"processed": False, "level": None}


def test_다른_사용자의_신청은_볼_수_없다(app):
    a, b = app.test_client(), app.test_client()
    signup(a, "dyn_user06"); login(a, "dyn_user06")
    signup(b, "dyn_user07"); login(b, "dyn_user07")
    app_id = a.post("/api/cavp/applications", json={"algorithm_type": "AES"}).get_json()["id"]
    assert b.get(f"/api/cavp/applications/{app_id}").status_code == 403
    assert b.get("/api/cavp/applications/99999").status_code == 404


def test_같은_신청_동시_요청은_한_건만_저장된다_DF13(app):
    seed = app.test_client()
    signup(seed, "dyn_user08"); login(seed, "dyn_user08")
    cookie = seed.get_cookie("session").value
    codes = []

    def run():
        c = app.test_client()
        c.set_cookie("session", cookie)
        codes.append(c.post("/api/cavp/applications", json={"algorithm_type": "AES"}).status_code)
    ts = [threading.Thread(target=run) for _ in range(16)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert codes.count(201) == 1 and codes.count(409) == 15
    assert seed.get("/api/cavp/applications").get_json()["total"] == 1


def test_승인과_반려_동시_요청은_한_건만_반영된다_DF14(app):
    user, inst = app.test_client(), app.test_client()
    signup(user, "dyn_user09"); login(user, "dyn_user09")
    signup(inst, "dyn_inst09", "institution", "ORG-1"); login(inst, "dyn_inst09")
    app_id = user.post("/api/cavp/applications", json={"algorithm_type": "AES"}).get_json()["id"]
    inst.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "reviewing"})
    cookie, codes = inst.get_cookie("session").value, []

    def run(target):
        c = app.test_client()
        c.set_cookie("session", cookie)
        codes.append(c.patch(f"/api/cavp/applications/{app_id}/status", json={"status": target}).status_code)
    ts = [threading.Thread(target=run, args=(t,)) for t in ["approved", "rejected"] * 8]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert codes.count(200) == 1 and codes.count(409) == 15


def test_테이블_이름이_없으면_기동하지_않는다():
    with pytest.raises(RuntimeError, match="DYNAMODB_TABLE"):
        create_app({"TESTING": True, "STORE_BACKEND": "dynamodb", "DYNAMODB_TABLE": ""})


def test_알_수_없는_저장소_종류는_기동하지_않는다():
    with pytest.raises(RuntimeError, match="STORE_BACKEND"):
        create_app({"TESTING": True, "STORE_BACKEND": "mysql"})
