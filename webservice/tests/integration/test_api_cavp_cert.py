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


# ---------------- 신청 취소 ----------------
def cancel(c, app_id):
    return c.post(f"/api/cavp/applications/{app_id}/cancel")


@case("IT-46", "FR-03", "POST /api/cavp/applications/{id}/cancel: 본인 접수 대기 취소", "200 status=cancelled·status_label=취소, 목록 필터와 상세에 반영, 같은 알고리즘 재신청 201")
def test_cancel_flow(login_as, db):
    c, _ = login_as()
    app_id = apply(c, "AES").get_json()["id"]
    r = cancel(c, app_id)
    assert r.status_code == 200 and r.get_json()["status"] == "cancelled" and r.get_json()["status_label"] == "취소"
    assert c.get(f"/api/cavp/applications/{app_id}").get_json()["status"] == "cancelled"
    assert c.get("/api/cavp/applications?status=cancelled").get_json()["total"] == 1
    assert apply(c, "AES").status_code == 201
    db.expire_all()
    assert db.get(CavpApplication, app_id).status == "cancelled"


@case("IT-47", "FR-03", "취소 불가 상태·없는 신청", "심사 시작 후 409 INVALID_TRANSITION, 이미 취소 409, 없는 id 404, 상태 불변", "negative")
def test_cancel_errors(login_as, db):
    person, _ = login_as(username="person01")
    officer, _ = login_as("institution", "officer01")
    app_id = apply(person).get_json()["id"]
    officer.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "reviewing"})
    r = cancel(person, app_id)
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "INVALID_TRANSITION"
    other = apply(person, "RSA").get_json()["id"]
    assert cancel(person, other).status_code == 200
    assert cancel(person, other).status_code == 409
    assert cancel(person, 99999).status_code == 404
    db.expire_all()
    assert db.get(CavpApplication, app_id).status == "reviewing"


@case("IT-48", "FR-03", "취소 권한: 타인·기관·비로그인", "타인과 기관 403 FORBIDDEN, 비로그인 401, 상태 불변", "security")
def test_cancel_permission(login_as, make_client, db):
    owner, _ = login_as(username="person01")
    stranger, _ = login_as(username="person02")
    officer, _ = login_as("institution", "officer01")
    app_id = apply(owner).get_json()["id"]
    for c in (stranger, officer):
        r = cancel(c, app_id)
        assert r.status_code == 403 and r.get_json()["error"]["code"] == "FORBIDDEN"
    assert cancel(make_client(), app_id).status_code == 401
    db.expire_all()
    assert db.get(CavpApplication, app_id).status == "submitted"


@case("IT-49", "FR-03", "PATCH status 로 취소 시도", "기관이 status=cancelled 로 바꾸려 하면 409 INVALID_TRANSITION, 상태 불변", "security")
def test_patch_cannot_cancel(login_as, db):
    person, _ = login_as(username="person01")
    officer, _ = login_as("institution", "officer01")
    app_id = apply(person).get_json()["id"]
    r = officer.patch(f"/api/cavp/applications/{app_id}/status", json={"status": "cancelled"})
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "INVALID_TRANSITION"
    db.expire_all()
    assert db.get(CavpApplication, app_id).status == "submitted"


@case("IT-50", "FR-03", "대시보드의 취소 집계", "by_status.cancelled 증가, in_progress 감소", "boundary")
def test_dashboard_counts_cancelled(login_as):
    c, _ = login_as()
    a = apply(c, "AES").get_json()["id"]; apply(c, "RSA")
    assert c.get("/api/dashboard").get_json()["applications"]["in_progress"] == 2
    cancel(c, a)
    d = c.get("/api/dashboard").get_json()["applications"]
    assert d["in_progress"] == 1 and d["by_status"]["cancelled"] == 1 and d["total"] == 2


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


# ---------------- SC-08 관리자 대시보드 ----------------
@case("IT-51", "FR-06", "GET /api/admin/summary: 기관 사용자", "200, applications/certificates/recent_applications/attention 키, 타인 신청 포함 집계")
def test_admin_summary_ok(login_as, db):
    officer, _ = login_as("institution", "officer01")
    a, ua = login_as(username="person01")
    b, ub = login_as(username="person02")
    factories.make_application(db, ua, "AES", "submitted"); factories.make_application(db, ub, "RSA", "approved")
    d = officer.get("/api/admin/summary").get_json()
    assert {"applications", "certificates", "recent_applications", "attention"} <= set(d)
    assert d["applications"]["total"] == 2 and d["applications"]["pending_review"] == 1
    assert {r["owner"] for r in d["recent_applications"]} == {"person01", "person02"}


@case("IT-52", "FR-06", "GET /api/admin/summary: 접근 통제", "개인·기업 403 FORBIDDEN, 비로그인 401 AUTHENTICATION_FAILED", "security")
def test_admin_summary_access_control(login_as, make_client):
    for kind in ("individual", "company"):
        c, _ = login_as(kind, f"{kind}01")
        r = c.get("/api/admin/summary")
        assert r.status_code == 403 and r.get_json()["error"]["code"] == "FORBIDDEN"
    r = make_client().get("/api/admin/summary")
    assert r.status_code == 401 and r.get_json()["error"]["code"] == "AUTHENTICATION_FAILED"


@case("IT-53", "FR-06", "GET /api/admin/summary: 취소·상태 변경이 집계에 반영", "취소하면 cancelled 증가·in_progress 감소, 심사 시작하면 pending_review 감소")
def test_admin_summary_follows_changes(login_as):
    officer, _ = login_as("institution", "officer01")
    person, _ = login_as(username="person01")
    first = apply(person, "AES").get_json()["id"]; second = apply(person, "RSA").get_json()["id"]
    assert officer.get("/api/admin/summary").get_json()["applications"]["pending_review"] == 2
    cancel(person, first)
    officer.patch(f"/api/cavp/applications/{second}/status", json={"status": "reviewing"})
    a = officer.get("/api/admin/summary").get_json()["applications"]
    assert a["by_status"]["cancelled"] == 1 and a["pending_review"] == 0 and a["in_progress"] == 1


@case("IT-54", "FR-06", "GET /admin 페이지 접근", "기관 200, 개인 /dashboard 이동, 비로그인 로그인 화면 이동", "security")
def test_admin_page_access(login_as, make_client):
    officer, _ = login_as("institution", "officer01")
    person, _ = login_as(username="person01")
    assert officer.get("/admin").status_code == 200
    r = person.get("/admin")
    assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard")
    r = make_client().get("/admin")
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    assert "관리자 대시보드" in officer.get("/dashboard").get_data(as_text=True)
    assert "관리자 대시보드" not in person.get("/dashboard").get_data(as_text=True)


# ---------------- 보안 정책(CSP) / 성능 ----------------
@case("IT-55", "NFR-보안", "모든 화면의 인라인 스크립트 제거와 CSP script-src 'self'", "화면 HTML 에 src 없는 script 와 on* 속성이 없고, CSP 가 script-src 'self'·frame-ancestors 'none' 을 포함, 스크립트 파일은 200 으로 제공", "security")
def test_pages_have_no_inline_script(login_as, make_client):
    import re
    officer, _ = login_as("institution", "officer01")
    for path in ("/", "/dashboard", "/privacy", "/cavp/apply", "/cavp/status", "/certificates", "/tamper", "/admin"):
        c = make_client() if path == "/" else officer  # 로그인 화면은 로그인하지 않은 상태에서만 열린다
        r = c.get(path)
        html = r.get_data(as_text=True)
        assert r.status_code == 200, path
        csp = r.headers["Content-Security-Policy"]
        assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "'unsafe-inline'" not in csp.split("style-src")[0], path
        assert not re.search(r"<script(?![^>]*\ssrc=)[^>]*>", html), path
        assert not re.search(r"\son(click|change|submit|load|error|input)=", html), path
        for src in re.findall(r'<script[^>]*\ssrc="([^"]+)"', html):
            js = c.get(src)
            assert js.status_code == 200 and "javascript" in js.headers["Content-Type"], src


@case("IT-56", "NFR-성능", "주요 조회 응답 시간(더미 데이터 300건)", "신청 목록·대시보드·관리자 요약·검증서 목록이 각각 2초 이내", "boundary")
def test_response_time_under_two_seconds(login_as, db):
    import time
    officer, _ = login_as("institution", "officer01")
    person, u = login_as(username="person01")
    from app.services.cavp_service import ALGORITHMS
    for i in range(300):
        factories.make_application(db, u, ALGORITHMS[i % len(ALGORITHMS)], "cancelled")
    for path, c in (("/api/cavp/applications?per_page=50", person), ("/api/dashboard", person),
                    ("/api/admin/summary", officer), ("/api/certificates", officer)):
        t0 = time.perf_counter()
        r = c.get(path)
        elapsed = time.perf_counter() - t0
        assert r.status_code == 200 and elapsed < 2.0, (path, elapsed)
