"""공격(결함 탐색) 시험 — SC-06 검증서 이력 조회 / SC-07 위변조 탐지.

검증서는 '정상'이라는 판정 자체가 가치이므로, 발급 권한·타인 조회·판정 조작·이상한 입력·동시 발급을 집중해서 깨 본다.
각 시험은 안전하게 동작해야 하는 쪽을 단언한다(실패하면 곧 결함).
"""
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import create_app
from app.models import Certificate
from tests import factories
from tests.case_registry import case
from tests.integration.conftest import login


def apply(c, algo="AES"):
    return c.post("/api/cavp/applications", json={"algorithm_type": algo}).get_json()["id"]


def approve(officer, app_id):
    for st in ("reviewing", "approved"):
        assert officer.patch(f"/api/cavp/applications/{app_id}/status", json={"status": st}).status_code == 200


def issue(officer, app_id, content="CERT-BODY", cert_type="CAVP"):
    return officer.post(f"/api/cavp/applications/{app_id}/certificate", json={"cert_type": cert_type, "content": content})


@pytest.fixture()
def world(login_as):
    person, _ = login_as(username="person01")
    officer, _ = login_as("institution", "officer01")
    stranger, _ = login_as(username="stranger01")
    app_id = apply(person)
    approve(officer, app_id)
    return person, officer, stranger, app_id


def n_certs(db):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Certificate))


@case("IT-ATK-51", "FR-04", "로그인하지 않고 검증서 발급·목록·상세·검증 호출", "모두 401, 검증서 0건", "security")
def test_certificate_apis_require_login(client, db):
    assert client.post("/api/cavp/applications/1/certificate", json={"cert_type": "CAVP", "content": "x"}).status_code == 401
    for url in ("/api/certificates", "/api/certificates/1", "/api/certificates/1/verify"):
        assert client.get(url).status_code == 401
    assert n_certs(db) == 0


@case("IT-ATK-52", "FR-04", "신청 당사자(개인·기업)가 자기 신청에 직접 검증서 발급", "403, 검증서 0건", "security")
@pytest.mark.parametrize("utype", ["individual", "company"])
def test_owner_cannot_issue_own_certificate(login_as, db, utype):
    owner, _ = login_as(utype, f"own_{utype}")
    officer, _ = login_as("institution", "officer01")
    app_id = apply(owner)
    approve(officer, app_id)
    assert issue(owner, app_id).status_code == 403
    assert n_certs(db) == 0


@case("IT-ATK-53", "FR-04", "같은 신청에 여러 기관 계정이 동시에 검증서 발급", "정확히 1건만 201, 나머지 409, 저장된 검증서 1건", "security")
def test_concurrent_issue_single_certificate(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "t" * 32, "DATABASE_URL": f"sqlite:///{tmp_path}/c.db",
                      "CERT_STORAGE_DIR": str(tmp_path / "certs")})
    s = app.session_factory()
    person = factories.make_user(s, username="racer_p")
    a = factories.make_application(s, person, "AES", "approved")
    officers = [factories.make_user(s, username=f"racer_o{i}", user_type="institution") for i in range(8)]
    s.close()
    clients = []
    for o in officers:
        c = app.test_client(); assert login(c, o.username).status_code == 200; clients.append(c)

    def job(i):
        return issue(clients[i], a.id, f"BODY-{i}").status_code
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(job, range(8)))
    assert sorted(codes) == [201] + [409] * 7, codes
    s = app.session_factory()
    assert s.scalar(select(func.count()).select_from(Certificate)) == 1
    s.close()


@case("IT-ATK-54", "FR-04", "검증서 내용 크기·자료형 경계", "60000바이트 성공, 60001바이트·빈 값·숫자·목록·null 은 400, 기록 증가 없음", "negative")
def test_content_bounds(world, db):
    person, officer, _, app_id = world
    for bad in ("", 123, ["x"], None, {"a": 1}, "a" * 60001):
        assert issue(officer, app_id, content=bad).status_code == 400, bad
    assert issue(officer, app_id, content="가" * 20001).status_code in (400, 413)   # 60003바이트(UTF-8)
    assert n_certs(db) == 0
    assert issue(officer, app_id, content="a" * 60000).status_code == 201


@case("IT-ATK-55", "FR-04", "검증서 유형 변형(소문자·공백·null·목록·긴 문자열)", "모두 400", "negative")
@pytest.mark.parametrize("ctype", ["cavp", "CAVP ", " KCMVP", None, ["CAVP"], "C" * 10000, "", "CAVP\n"])
def test_cert_type_variants(world, db, ctype):
    _, officer, _, app_id = world
    assert issue(officer, app_id, cert_type=ctype).status_code == 400
    assert n_certs(db) == 0


@case("IT-ATK-56", "FR-04", "타인·무관한 사용자가 검증서 상세·검증 호출, 존재하지 않는 id, 비정상 경로", "타인 403, 없는 id 404, 경로 조작은 404/405", "security")
def test_stranger_and_odd_paths(world):
    person, officer, stranger, app_id = world
    cid = issue(officer, app_id).get_json()["id"]
    assert stranger.get(f"/api/certificates/{cid}").status_code == 403
    assert stranger.get(f"/api/certificates/{cid}/verify").status_code == 403
    assert person.get(f"/api/certificates/{cid}").status_code == 200
    assert officer.get(f"/api/certificates/{cid}").status_code == 200   # 기관은 신청처럼 전체 조회 가능
    for url in ("/api/certificates/0", "/api/certificates/-1", "/api/certificates/99999999999999999999",
                f"/api/certificates/{cid}/../1", "/api/certificates/%2e%2e%2fetc", f"/api/certificates/{cid}%00"):
        assert person.get(url).status_code in (404, 405, 400), url
    assert stranger.post(f"/api/certificates/{cid}/verify").status_code == 405


@case("IT-ATK-57", "FR-05", "타인이 검증을 호출해도 상태가 바뀌지 않고, 응답에 해시·내용·경로가 없음", "403, 상태 불변, 64자 hex·내용·저장경로 비노출", "security")
def test_no_leak_and_no_state_change_by_stranger(world, app, db):
    person, officer, stranger, app_id = world
    cid = issue(officer, app_id, content="TOP-SECRET-BODY").get_json()["id"]
    f = Path(app.config["CERT_STORAGE_DIR"]) / f"cert_{cid}.bin"
    f.write_text("tampered")
    assert stranger.get(f"/api/certificates/{cid}/verify").status_code == 403
    db.expire_all()
    assert db.get(Certificate, cid).tamper_status == "normal"      # 권한 없는 호출은 판정을 바꾸지 못한다
    for url in (f"/api/certificates/{cid}", f"/api/certificates/{cid}/verify", "/api/certificates"):
        text = person.get(url).get_data(as_text=True)
        assert not re.search(r"[0-9a-f]{64}", text) and "TOP-SECRET-BODY" not in text
        assert app.config["CERT_STORAGE_DIR"] not in text


@case("IT-ATK-58", "FR-05", "저장된 검증서 파일을 폴더·빈 파일·심볼릭 링크 등으로 바꿔치기", "모두 200 + suspected (서버 오류 아님)", "security")
@pytest.mark.parametrize("how", ["dir", "empty", "other_cert_copy"])
def test_replaced_storage_object(world, app, how):
    person, officer, _, app_id = world
    cid = issue(officer, app_id).get_json()["id"]
    f = Path(app.config["CERT_STORAGE_DIR"]) / f"cert_{cid}.bin"
    f.unlink()
    if how == "dir":
        f.mkdir()
    elif how == "empty":
        f.write_bytes(b"")
    else:   # 다른 검증서(내용이 다름)의 파일을 복사해 덮어쓰기
        other_app = apply(person, "RSA"); approve(officer, other_app)
        ocid = issue(officer, other_app, "ANOTHER-BODY").get_json()["id"]
        shutil.copy(Path(app.config["CERT_STORAGE_DIR"]) / f"cert_{ocid}.bin", f)
    r = person.get(f"/api/certificates/{cid}/verify")
    assert r.status_code == 200 and r.get_json()["tamper_status"] == "suspected"


@case("IT-ATK-59", "FR-05", "변조 → 의심 → 원복 → 정상 전환, 그리고 변조 상태에서 동시 검증 다발", "판정이 파일 상태를 그대로 따르고 동시 호출도 모두 200", "boundary")
def test_verify_follows_file_state_and_concurrent(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "t" * 32, "DATABASE_URL": f"sqlite:///{tmp_path}/v.db",
                      "CERT_STORAGE_DIR": str(tmp_path / "certs")})
    s = app.session_factory()
    person = factories.make_user(s, username="verif_p")
    officer = factories.make_user(s, username="verif_o", user_type="institution")
    a = factories.make_application(s, person, "AES", "approved"); s.close()
    oc = app.test_client(); login(oc, officer.username)
    cid = issue(oc, a.id, "ORIGINAL").get_json()["id"]
    f = Path(app.config["CERT_STORAGE_DIR"]) / f"cert_{cid}.bin"
    f.write_text("evil")
    clients = []
    for _ in range(6):
        c = app.test_client(); assert login(c, person.username).status_code == 200; clients.append(c)
    with ThreadPoolExecutor(6) as ex:
        results = list(ex.map(lambda c: c.get(f"/api/certificates/{cid}/verify").status_code, clients))
    assert results == [200] * 6
    assert clients[0].get(f"/api/certificates/{cid}").get_json()["tamper_status"] == "suspected"
    f.write_text("ORIGINAL")
    assert clients[0].get(f"/api/certificates/{cid}/verify").get_json()["tamper_status"] == "normal"


@case("IT-ATK-60", "FR-04", "검증서 목록의 쿼리 파라미터 경계(page·per_page 이상값)", "모두 400, 서버 오류 없음", "negative")
@pytest.mark.parametrize("q", ["page=0", "page=-1", "per_page=0", "per_page=51", "page=abc", "per_page=1.5", "page=99999999999999999999"])
def test_list_query_bounds(world, q):
    person, *_ = world
    assert person.get(f"/api/certificates?{q}").status_code == 400


@case("IT-ATK-61", "FR-04", "승인 전 신청에 발급 시도 후 승인하고 다시 발급 / 반려된 신청 발급", "승인 전·반려는 409, 승인 후 1건만", "negative")
def test_issue_only_after_approval(login_as, db):
    person, _ = login_as(username="person01")
    officer, _ = login_as("institution", "officer01")
    a = apply(person)
    assert issue(officer, a).status_code == 409
    officer.patch(f"/api/cavp/applications/{a}/status", json={"status": "reviewing"})
    assert issue(officer, a).status_code == 409
    officer.patch(f"/api/cavp/applications/{a}/status", json={"status": "rejected"})
    assert issue(officer, a).status_code == 409
    assert n_certs(db) == 0
    b = apply(person, "RSA"); approve(officer, b)
    assert issue(officer, b).status_code == 201 and n_certs(db) == 1


@case("IT-ATK-62", "FR-03", "아주 큰 번호(DB 정수 한도 초과)로 사용자·신청·검증서 조회 (DF-16)", "404 (서버 오류 500 아님)", "negative")
@pytest.mark.parametrize("big", ["9223372036854775808", "99999999999999999999", "1" + "0" * 400])
def test_huge_ids_are_not_found(login_as, big):
    officer, _ = login_as("institution", "officer01")
    assert officer.get(f"/api/cavp/applications/{big}").status_code == 404
    assert officer.patch(f"/api/cavp/applications/{big}/status", json={"status": "reviewing"}).status_code == 404
    assert officer.post(f"/api/cavp/applications/{big}/certificate", json={"cert_type": "CAVP", "content": "x"}).status_code == 404
    assert officer.get(f"/api/certificates/{big}").status_code == 404
    assert officer.get(f"/api/certificates/{big}/verify").status_code == 404
