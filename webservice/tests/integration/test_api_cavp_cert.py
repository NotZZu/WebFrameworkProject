"""통합시험 IT — FR-03 CAVP 신청 API / FR-04·05 검증서 API / D12 초기데이터."""
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import CavpApplication, Certificate
from app.seed import seed
from tests import factories
from tests.case_registry import case
from tests.integration.conftest import login


def apply(c, algo="AES"):
    return c.post("/api/cavp/applications", json={"algorithm_type": algo})


def n(db, model):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model))


# ---------------- CAVP ----------------
@case("IT-18", "FR-03", "POST /api/cavp/applications → GET 목록", "201 status=submitted, 목록 응답에 방금 신청 포함")
def test_create_and_list(login_as, db):
    c, u = login_as()
    r = apply(c, "RSA")
    assert r.status_code == 201 and r.get_json()["status"] == "submitted" and r.get_json()["algorithm_type"] == "RSA"
    lst = c.get("/api/cavp/applications").get_json()
    assert lst["total"] == 1 and lst["items"][0]["id"] == r.get_json()["id"]
    assert n(db, CavpApplication) == 1


@case("IT-19", "FR-03", "신청 입력 오류/중복", "미허용 알고리즘 400, 진행 중 중복 409(DUPLICATE_APPLICATION), 레코드 증가 없음", "negative")
def test_create_errors(login_as, db):
    c, _ = login_as()
    for bad in ({"algorithm_type": ""}, {"algorithm_type": "MD5"}, {}):
        r = c.post("/api/cavp/applications", json=bad)
        assert r.status_code == 400 and r.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert apply(c).status_code == 201
    r = apply(c)
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "DUPLICATE_APPLICATION"
    assert n(db, CavpApplication) == 1


@case("IT-20", "FR-03", "신청 목록: 상태 필터·페이지네이션 쿼리", "status/page/per_page 가 반영되고 total 이 필터 기준", "boundary")
def test_list_query_params(login_as, db):
    c, u = login_as()
    for i in range(12):
        factories.make_application(db, u, "AES", "approved")
    factories.make_application(db, u, "RSA", "submitted")
    p2 = c.get("/api/cavp/applications?page=2&per_page=5").get_json()
    assert p2["total"] == 13 and len(p2["items"]) == 5 and p2["page"] == 2
    assert c.get("/api/cavp/applications?status=submitted").get_json()["total"] == 1


@case("IT-21", "FR-03", "신청 목록: 잘못된 쿼리 파라미터", "page=0, per_page=51, per_page=abc, status=weird → 400", "negative")
@pytest.mark.parametrize("qs", ["page=0", "per_page=51", "per_page=abc", "status=weird"])
def test_list_bad_query(login_as, qs):
    c, _ = login_as()
    r = c.get(f"/api/cavp/applications?{qs}")
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "VALIDATION_ERROR"


@case("IT-22", "FR-03", "신청 조회 격리: 타인 신청 목록/상세", "목록에 타인 건 없음, 타인 상세 403 FORBIDDEN, 없는 id 404", "security")
def test_application_isolation(login_as, db):
    a, ua = login_as(username="usera01")
    b, ub = login_as(username="userb01")
    app_a = apply(a).get_json()
    assert b.get("/api/cavp/applications").get_json()["total"] == 0
    r = b.get(f"/api/cavp/applications/{app_a['id']}")
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "FORBIDDEN"
    assert a.get(f"/api/cavp/applications/{app_a['id']}").status_code == 200
    assert a.get("/api/cavp/applications/99999").status_code == 404


@case("IT-23", "FR-03", "PATCH /api/cavp/applications/{id}/status: 기관 심사 흐름", "submitted→reviewing→approved 200, 잘못된 전이 409 INVALID_TRANSITION, 기관은 타인 신청 상세 조회 가능")
def test_status_flow_by_institution(login_as, db):
    person, _ = login_as(username="person01")
    officer, _ = login_as("institution", "officer01")
    app_id = apply(person).get_json()["id"]
    assert officer.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "reviewing"}).get_json()["status"] == "reviewing"
    r = officer.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "submitted"})
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "INVALID_TRANSITION"
    assert officer.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "approved"}).status_code == 200
    assert officer.get(f"/api/cavp/applications/{app_id}").status_code == 200
    assert person.get(f"/api/cavp/applications/{app_id}").get_json()["status"] == "approved"


@case("IT-24", "FR-03", "PATCH status: 기관이 아닌 사용자 / 알 수 없는 상태", "403 FORBIDDEN / 400 VALIDATION_ERROR, 상태 불변", "security")
def test_status_change_forbidden(login_as, db):
    person, _ = login_as(username="person01")
    officer, _ = login_as("institution", "officer01")
    app_id = apply(person).get_json()["id"]
    r = person.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "reviewing"})
    assert r.status_code == 403
    r = officer.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "weird"})
    assert r.status_code == 400
    db.expire_all()
    assert db.get(CavpApplication, app_id).status == "submitted"


# ---------------- Certificates ----------------
def approved_application_via_api(person, officer):
    app_id = apply(person).get_json()["id"]
    officer.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "reviewing"})
    officer.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "approved"})
    return app_id


def issue(officer, app_id, content="CERT-BODY-v1", cert_type="CAVP"):
    return officer.post(f"/api/cavp/applications/{app_id}/certificate", json={"cert_type": cert_type, "content": content})


@case("IT-25", "FR-04", "POST /api/cavp/applications/{id}/certificate: 승인 건 발급", "201, tamper_status=normal, 소유자의 /api/certificates 목록·상세에 노출")
def test_issue_and_list(login_as, db):
    person, _ = login_as(username="person01")
    officer, _ = login_as("institution", "officer01")
    app_id = approved_application_via_api(person, officer)
    r = issue(officer, app_id)
    assert r.status_code == 201 and r.get_json()["tamper_status"] == "normal"
    cid = r.get_json()["id"]
    lst = person.get("/api/certificates").get_json()
    assert lst["total"] == 1 and lst["items"][0]["id"] == cid
    assert person.get(f"/api/certificates/{cid}").status_code == 200


@case("IT-26", "FR-04", "검증서 발급 오류 경로", "미승인 신청 409, 중복 발급 409, 비기관 403, 잘못된 cert_type 400, 레코드 증가 없음", "negative")
def test_issue_errors(login_as, db):
    person, _ = login_as(username="person01")
    officer, _ = login_as("institution", "officer01")
    pending = apply(person).get_json()["id"]
    assert issue(officer, pending).status_code == 409
    officer.patch(f"/api/cavp/applications/{pending}/status", json={"status": "reviewing"})
    officer.patch(f"/api/cavp/applications/{pending}/status", json={"status": "approved"})
    assert issue(person, pending).status_code == 403
    assert issue(officer, pending, cert_type="XYZ").status_code == 400
    assert issue(officer, pending).status_code == 201
    assert issue(officer, pending).status_code == 409
    assert n(db, Certificate) == 1


@case("IT-27", "FR-05", "GET /api/certificates/{id}/verify: 정상 건 / 위변조 의심 건", "tamper_status 값에 따라 판정 필드 일치(normal / suspected)")
def test_verify_normal_vs_suspected(login_as, app, db):
    person, _ = login_as(username="person01")
    officer, _ = login_as("institution", "officer01")
    cid = issue(officer, approved_application_via_api(person, officer)).get_json()["id"]
    assert person.get(f"/api/certificates/{cid}/verify").get_json()["tamper_status"] == "normal"
    (Path(app.config["CERT_STORAGE_DIR"]) / f"cert_{cid}.bin").write_text("TAMPERED")
    assert person.get(f"/api/certificates/{cid}/verify").get_json()["tamper_status"] == "suspected"
    assert person.get(f"/api/certificates/{cid}").get_json()["tamper_status"] == "suspected"


@case("IT-28", "FR-05", "검증서 파일 삭제 후 verify", "200 + suspected (서버 오류 500 아님)", "negative")
def test_verify_missing_file(login_as, app):
    person, _ = login_as(username="person01")
    officer, _ = login_as("institution", "officer01")
    cid = issue(officer, approved_application_via_api(person, officer)).get_json()["id"]
    (Path(app.config["CERT_STORAGE_DIR"]) / f"cert_{cid}.bin").unlink()
    r = person.get(f"/api/certificates/{cid}/verify")
    assert r.status_code == 200 and r.get_json()["tamper_status"] == "suspected"


@case("IT-29", "FR-04", "검증서 조회 격리", "타인의 검증서 상세·verify 403, 목록에 타인 건 없음, 없는 id 404", "security")
def test_certificate_isolation(login_as, db):
    person, _ = login_as(username="person01")
    stranger, _ = login_as(username="stranger01")
    officer, _ = login_as("institution", "officer01")
    cid = issue(officer, approved_application_via_api(person, officer)).get_json()["id"]
    assert stranger.get(f"/api/certificates/{cid}").status_code == 403
    assert stranger.get(f"/api/certificates/{cid}/verify").status_code == 403
    assert stranger.get("/api/certificates").get_json()["total"] == 0
    assert person.get("/api/certificates/99999").status_code == 404


@case("IT-30", "FR-05", "검증서 응답 보안: 서버 파일 경로·해시 원문 비노출", "응답 본문에 저장 디렉터리 경로 없음", "security")
def test_certificate_response_hides_server_paths(login_as, app):
    person, _ = login_as(username="person01")
    officer, _ = login_as("institution", "officer01")
    cid = issue(officer, approved_application_via_api(person, officer)).get_json()["id"]
    storage = app.config["CERT_STORAGE_DIR"]
    for url in (f"/api/certificates/{cid}", f"/api/certificates/{cid}/verify", "/api/certificates"):
        assert storage not in person.get(url).get_data(as_text=True)


# ---------------- Flow / seed ----------------
@case("IT-31", "FR-14", "E2E: 가입→로그인→가명처리→신청→심사→발급→조회→변조탐지", "전 단계 성공, 변조 후 suspected", "positive")
def test_end_to_end_flow(make_client, app, db):
    user, officer = make_client(), make_client()
    assert user.post("/api/auth/signup", json={"username": "e2e_user", "password": "Passw0rd1", "user_type": "individual"}).status_code == 201
    assert officer.post("/api/auth/signup", json={"username": "e2e_org", "password": "Passw0rd1", "user_type": "institution", "org_code": "NSR"}).status_code == 201
    assert login(user, "e2e_user").status_code == 200 and login(officer, "e2e_org").status_code == 200
    assert user.post("/api/privacy/process", json={"mode": "pseudonym", "name": "홍길동", "birthdate": "1990-04-12"}).status_code == 200
    app_id = apply(user, "SHA-3").get_json()["id"]
    assert user.get("/api/cavp/applications").get_json()["items"][0]["status"] == "submitted"
    for st in ("reviewing", "approved"):
        assert officer.patch(f"/api/cavp/applications/{app_id}/status", json={"status": st}).status_code == 200
    cid = issue(officer, app_id).get_json()["id"]
    assert user.get("/api/certificates").get_json()["total"] == 1
    assert user.get(f"/api/certificates/{cid}/verify").get_json()["tamper_status"] == "normal"
    (Path(app.config["CERT_STORAGE_DIR"]) / f"cert_{cid}.bin").write_text("evil")
    assert user.get(f"/api/certificates/{cid}/verify").get_json()["tamper_status"] == "suspected"
    assert user.post("/api/auth/logout").status_code == 204


@case("IT-32", "FR-04", "초기데이터(seed) 적재 후 데모 계정으로 화면 데이터 조회", "demo_individual 로그인 → 신청/검증서 목록 존재, 위변조 의심 건 1건 확인(기관 계정)")
def test_seeded_demo_accounts(app, db, make_client):
    seed(db)
    person, officer = make_client(), make_client()
    assert login(person, "demo_individual", "Demo1234").status_code == 200
    assert login(officer, "demo_institution", "Demo1234").status_code == 200
    assert person.get("/api/cavp/applications").get_json()["total"] >= 1
    db.expire_all()
    suspected = db.scalars(select(Certificate).where(Certificate.tamper_status == "suspected")).all()
    assert len(suspected) == 1
