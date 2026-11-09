"""시스템시험 ST-09 (브라우저 E2E) — SC-08 관리자 대시보드. Playwright 필요(없으면 건너뜀)."""
import os
import pathlib
import socket
import threading

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
from werkzeug.serving import make_server  # noqa: E402

from app import create_app  # noqa: E402
from tests import factories  # noqa: E402
from tests.case_registry import case  # noqa: E402

ART = pathlib.Path(os.environ.get("E2E_ARTIFACT_DIR", "test-artifacts"))


@pytest.fixture(scope="module")
def srv():
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite://", "SECRET_KEY": "e2e"})
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield app, f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture()
def browser_page():
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            pytest.skip("Chromium 실행 불가")
        yield browser.new_page(viewport={"width": 1280, "height": 800}, bypass_csp=True)  # 문자열 대기식이 CSP에 막혀 시험에서만 우회(CSP 동작은 ST-10)
        browser.close()


def shot(pg, name):
    ART.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(ART / f"{name}.png"))


def login(pg, base, username, user_type="individual"):
    pg.goto(base + "/")
    pg.click(f"#tabs button[data-type='{user_type}']")
    pg.fill("#username", username); pg.fill("#password", factories.DEFAULT_PASSWORD)
    pg.click("#submit")
    pg.wait_for_url("**/dashboard")



# 관리자 화면은 전체 사용자 범위라 앞선 시험이 만든 신청이 보인다. 빈 상태 시험은 데이터를 만들기 전에 실행되도록 맨 앞에 둔다.
@case("ST-09-N2", "FR-06", "브라우저 E2E: 데이터가 없을 때의 관리자 화면", "수치 0, 신청·주의 사항 빈 안내 표시", "boundary")
def test_admin_empty(srv, browser_page):
    app, base = srv
    s = app.session_factory(); factories.make_user(s, username="adm_empty", user_type="institution"); s.close()
    login(browser_page, base, "adm_empty", "institution")
    browser_page.goto(base + "/admin")
    browser_page.wait_for_function("document.getElementById('kpi-total').textContent.trim() === '0'")
    assert "신청 내역이 없습니다" in browser_page.inner_text("#recent-body")
    assert "주의할 항목이 없습니다" in browser_page.inner_text("#attention")


def seed(app):
    s = app.session_factory()
    officer = factories.make_user(s, username="adm_officer", user_type="institution")
    p1 = factories.make_user(s, username="adm_p1"); p2 = factories.make_user(s, username="adm_p2")
    factories.make_application(s, p1, "AES", "submitted"); factories.make_application(s, p1, "RSA", "reviewing")
    a3 = factories.make_application(s, p2, "AES", "approved"); factories.make_application(s, p2, "HMAC", "cancelled")
    factories.make_certificate(s, a3, tamper_status="suspected")
    s.close()


@case("ST-09", "FR-06", "브라우저 E2E: 기관이 사이드 메뉴로 관리자 대시보드를 열어 전체 현황 확인",
      "전체 4건, 진행 중 2건, 심사 대기 1건, 위변조 의심 1건, 상태·알고리즘별 표와 최근 신청에 타인 신청 표시")
def test_admin_dashboard(srv, browser_page):
    app, base = srv
    seed(app)
    login(browser_page, base, "adm_officer", "institution")
    browser_page.click("nav a[href='/admin']")
    browser_page.wait_for_url("**/admin")
    browser_page.wait_for_function("document.getElementById('kpi-total').textContent.trim() === '4'")
    assert browser_page.inner_text("#kpi-in-progress").strip() == "2"
    assert browser_page.inner_text("#kpi-pending").strip() == "1"
    assert browser_page.inner_text("#kpi-suspected").strip() == "1"
    assert "취소" in browser_page.inner_text("#status-body") and "AES" in browser_page.inner_text("#algo-body")
    recent = browser_page.inner_text("#recent-body")
    assert "adm_p1" in recent and "adm_p2" in recent
    assert "위변조 의심" in browser_page.inner_text("#attention")
    shot(browser_page, "sc08_admin_1_summary")


@case("ST-09-N1", "FR-06", "브라우저 E2E: 개인 계정은 메뉴가 없고 주소로 들어가도 대시보드로 이동", "'관리자 대시보드' 메뉴 없음, /admin 직접 접속 시 /dashboard", "security")
def test_individual_blocked(srv, browser_page):
    app, base = srv
    s = app.session_factory(); factories.make_user(s, username="adm_plain"); s.close()
    login(browser_page, base, "adm_plain")
    assert browser_page.locator("nav a[href='/admin']").count() == 0
    browser_page.goto(base + "/admin")
    browser_page.wait_for_url("**/dashboard")


@case("ST-09-N3", "FR-06", "브라우저 E2E: 로그인하지 않고 관리자 화면 접근", "로그인 화면으로 이동", "security")
def test_admin_requires_login(srv, browser_page):
    app, base = srv
    browser_page.goto(base + "/admin")
    browser_page.wait_for_selector("#username")
