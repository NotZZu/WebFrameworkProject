"""시스템시험 ST-02 (브라우저 E2E) — SC-02 대시보드 화면. Playwright 필요(없으면 건너뜀)."""
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
        yield browser.new_page(viewport={"width": 1280, "height": 800})
        browser.close()


def shot(pg, name):
    ART.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(ART / f"{name}.png"))


def login(pg, base, username):
    pg.goto(base + "/")
    pg.fill("#username", username); pg.fill("#password", factories.DEFAULT_PASSWORD)
    pg.click("#submit")
    pg.wait_for_url("**/dashboard")


@case("ST-02", "FR-03", "브라우저 E2E: 대시보드 KPI·최근 신청·알림 표시", "로그인 후 인사말, KPI 4종 수치, 최근 신청 행과 상태 배지, 알림 문구 표시", "positive")
def test_dashboard_full(srv, browser_page):
    app, base = srv
    s = app.session_factory()
    u = factories.make_user(s, username="dash_full")
    factories.make_application(s, u, "AES", "reviewing")
    a = factories.make_application(s, u, "RSA", "approved")
    factories.make_certificate(s, a)
    s.close()
    login(browser_page, base, "dash_full")
    browser_page.wait_for_function("document.getElementById('kpi-in-progress').textContent.trim() === '1'")
    assert "dash_full" in browser_page.inner_text("#welcome")
    assert browser_page.inner_text("#kpi-certificates").strip() == "1"
    assert browser_page.inner_text("#kpi-suspected").strip() == "0"
    body = browser_page.inner_text("#recent-body")
    assert "AES" in body and "RSA" in body and "시험 진행중" in body and "시험 완료" in body
    assert "시험이 심사 중" in browser_page.inner_text("#notifications")
    shot(browser_page, "sc02_1_dashboard")


@case("ST-02-N1", "FR-03", "브라우저 E2E: 신규 사용자(데이터 없음) 빈 상태", "KPI 모두 0, '아직 신청 내역이 없습니다' 안내 표시", "negative")
def test_dashboard_empty(srv, browser_page):
    app, base = srv
    s = app.session_factory(); factories.make_user(s, username="dash_empty"); s.close()
    login(browser_page, base, "dash_empty")
    browser_page.wait_for_selector("#recent-empty")
    assert "아직 신청 내역이 없습니다" in browser_page.inner_text("#recent-empty")
    for k in ("in-progress", "certificates", "suspected", "privacy"):
        assert browser_page.inner_text(f"#kpi-{k}").strip() == "0"
    shot(browser_page, "sc02_2_empty")


@case("ST-02-N2", "FR-03", "브라우저 E2E: 위변조 의심 검증서 강조", "위변조 의심 KPI 가 1, 경고 알림과 검증서 번호(CV-)가 표시되고 경고 스타일 적용", "security")
def test_dashboard_suspected(srv, browser_page):
    app, base = srv
    s = app.session_factory()
    u = factories.make_user(s, username="dash_warn")
    a = factories.make_application(s, u, "AES", "approved")
    factories.make_certificate(s, a, tamper_status="suspected")
    s.close()
    login(browser_page, base, "dash_warn")
    browser_page.wait_for_function("document.getElementById('kpi-suspected').textContent.trim() === '1'")
    assert "위변조 의심" in browser_page.inner_text("#notifications")
    assert "CV-" in browser_page.inner_text("#notifications")
    assert browser_page.locator("#notifications .warning").count() >= 1
    shot(browser_page, "sc02_3_suspected")


@case("ST-02-N3", "FR-03", "브라우저 E2E: 대시보드에서 로그아웃", "로그아웃 후 로그인 화면 복귀, 뒤로가기/재접근 시 대시보드 접근 불가", "security")
def test_dashboard_logout(srv, browser_page):
    app, base = srv
    s = app.session_factory(); factories.make_user(s, username="dash_out"); s.close()
    login(browser_page, base, "dash_out")
    browser_page.wait_for_selector("#kpi-in-progress")
    browser_page.click("#logout")
    browser_page.wait_for_url(base + "/")
    browser_page.goto(base + "/dashboard")
    assert browser_page.url == base + "/"
