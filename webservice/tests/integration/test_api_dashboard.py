"""통합시험 IT — SC-02 대시보드 API(GET /api/dashboard) 및 페이지."""
from tests import factories
from tests.case_registry import case


@case("IT-33", "FR-03", "GET /api/dashboard: 로그인 사용자의 요약 구조", "200, scope/user/applications/certificates/privacy/recent_applications/notifications 키 포함", "positive")
def test_dashboard_structure(login_as, db):
    c, u = login_as()
    a = factories.make_application(db, u, "AES", "reviewing")
    factories.make_application(db, u, "RSA", "approved")
    r = c.get("/api/dashboard")
    assert r.status_code == 200
    d = r.get_json()
    assert {"scope", "user", "applications", "certificates", "privacy",
            "recent_applications", "notifications"} <= set(d)
    assert d["scope"] == "own" and d["user"]["username"] == u.username
    assert d["applications"]["total"] == 2 and d["applications"]["in_progress"] == 1
    assert a.id in [x["id"] for x in d["recent_applications"]]


@case("IT-34", "FR-03", "GET /api/dashboard: 비로그인 접근", "401 AUTHENTICATION_FAILED", "security")
def test_dashboard_requires_login(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 401 and r.get_json()["error"]["code"] == "AUTHENTICATION_FAILED"


@case("IT-35", "FR-03", "GET /api/dashboard: 사용자 간 데이터 격리", "A 의 신청/검증서 건수가 B 의 응답에 포함되지 않음", "security")
def test_dashboard_isolation(login_as, db):
    ca, ua = login_as()
    cb, ub = login_as()
    for _ in range(3):
        factories.make_application(db, ua, "AES", "submitted")
    factories.make_application(db, ub, "RSA", "submitted")
    assert ca.get("/api/dashboard").get_json()["applications"]["total"] == 3
    assert cb.get("/api/dashboard").get_json()["applications"]["total"] == 1


@case("IT-36", "FR-03", "GET /api/dashboard: 기관 사용자는 전체 범위", "scope=all, 타 사용자 신청도 집계에 포함", "positive")
def test_dashboard_institution_scope(login_as, db):
    ci, _ = login_as("institution")
    _, other = login_as()
    factories.make_application(db, other, "AES", "submitted")
    d = ci.get("/api/dashboard").get_json()
    assert d["scope"] == "all" and d["applications"]["total"] == 1


@case("IT-37", "FR-03", "GET /api/dashboard: 비밀번호/해시 비노출", "응답 본문에 password / hash 문자열 없음", "security")
def test_dashboard_no_secret(login_as):
    c, _ = login_as()
    r = c.get("/api/dashboard")
    assert r.status_code == 200, "대시보드 API 미구현 — 전제 조건 위반"
    body = r.get_data(as_text=True).lower()
    assert "password" not in body and "$2b$" not in body


@case("IT-38", "FR-03", "GET /api/dashboard: 데이터 변경 즉시 반영", "신청·위변조 의심 검증서 추가 후 재호출 시 건수·알림 증가", "positive")
def test_dashboard_reflects_changes(login_as, db):
    c, u = login_as()
    before = c.get("/api/dashboard").get_json()
    assert before["applications"]["total"] == 0 and before["notifications"] == []
    a = factories.make_application(db, u, "AES", "approved")
    factories.make_certificate(db, a, tamper_status="suspected")
    after = c.get("/api/dashboard").get_json()
    assert after["applications"]["total"] == 1 and after["certificates"]["suspected"] == 1
    assert after["notifications"] and after["notifications"][0]["type"] == "warning"


@case("IT-39", "FR-03", "GET /dashboard 페이지: 접근 제어와 화면 요소", "비로그인 302 → /, 로그인 시 #welcome/#kpi-in-progress/#recent-body/#notifications/#logout 포함", "positive")
def test_dashboard_page(client, login_as):
    r = client.get("/dashboard")
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    c, u = login_as()
    html = c.get("/dashboard").get_data(as_text=True)
    for marker in ("id=\"welcome\"", "id=\"kpi-in-progress\"", "id=\"kpi-certificates\"",
                   "id=\"kpi-suspected\"", "id=\"kpi-privacy\"", "id=\"recent-body\"",
                   "id=\"notifications\"", "id=\"logout\""):
        assert marker in html, marker
    assert u.username in html


@case("IT-40", "FR-03", "POST /api/dashboard: 허용되지 않은 메서드", "405 METHOD_NOT_ALLOWED JSON", "negative")
def test_dashboard_method_not_allowed(login_as):
    c, _ = login_as()
    r = c.post("/api/dashboard", json={})
    assert r.status_code == 405 and r.get_json()["error"]["code"] == "METHOD_NOT_ALLOWED"
