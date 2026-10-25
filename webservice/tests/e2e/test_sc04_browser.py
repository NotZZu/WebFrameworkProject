"""시스템시험 ST-04 (브라우저 E2E) — SC-04 CAVP 시험 신청 화면. Playwright 필요(없으면 건너뜀)."""
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


def new_user(app, name):
    s = app.session_factory(); factories.make_user(s, username=name); s.close()


@case("ST-04", "FR-03", "브라우저 E2E: 알고리즘을 골라 신청하면 성공 안내와 함께 내 신청 목록에 나타남",
      "성공 메시지 표시, 목록에 알고리즘·'접수 대기' 배지 행 1건, 화면 이동 없음")
def test_apply_success(srv, browser_page):
    app, base = srv
    new_user(app, "apply_ok")
    login(browser_page, base, "apply_ok")
    browser_page.goto(base + "/cavp/apply")
    browser_page.wait_for_selector("#algorithm option[value='RSA']", state="attached")
    assert browser_page.inner_text("#my-apps-body").count("RSA") == 0
    browser_page.select_option("#algorithm", "RSA")
    browser_page.click("#submit-app")
    browser_page.wait_for_function("document.getElementById('my-apps-body').innerText.includes('RSA')")
    assert "신청" in browser_page.inner_text("#apply-msg")
    assert "접수 대기" in browser_page.inner_text("#my-apps-body")
    assert browser_page.url.endswith("/cavp/apply")
    shot(browser_page, "sc04_1_success")


@case("ST-04-N1", "FR-03", "브라우저 E2E: 같은 알고리즘을 진행 중에 다시 신청", "오류 안내 표시, 목록은 1건 그대로", "negative")
def test_apply_duplicate(srv, browser_page):
    app, base = srv
    new_user(app, "apply_dup")
    login(browser_page, base, "apply_dup")
    browser_page.goto(base + "/cavp/apply")
    browser_page.wait_for_selector("#algorithm option[value='AES']", state="attached")
    browser_page.select_option("#algorithm", "AES"); browser_page.click("#submit-app")
    browser_page.wait_for_function("document.getElementById('my-apps-body').innerText.includes('AES')")
    browser_page.select_option("#algorithm", "AES"); browser_page.click("#submit-app")
    browser_page.wait_for_function("document.getElementById('apply-msg').classList.contains('err')")
    assert "진행 중" in browser_page.inner_text("#apply-msg")
    assert browser_page.locator("#my-apps-body tr").count() == 1
    shot(browser_page, "sc04_2_duplicate")


@case("ST-04-N2", "FR-03", "브라우저 E2E: 알고리즘을 고르지 않고 신청", "서버에 요청하지 않고 선택 안내 표시, 목록 변화 없음", "negative")
def test_apply_without_selection(srv, browser_page):
    app, base = srv
    new_user(app, "apply_none")
    login(browser_page, base, "apply_none")
    browser_page.goto(base + "/cavp/apply")
    browser_page.wait_for_selector("#algorithm option[value='AES']", state="attached")
    posts = []
    browser_page.on("request", lambda r: posts.append(r) if r.method == "POST" else None)
    browser_page.click("#submit-app")
    browser_page.wait_for_function("document.getElementById('apply-msg').classList.contains('err')")
    assert "선택" in browser_page.inner_text("#apply-msg")
    assert posts == []
    assert "아직 신청 내역이 없습니다" in browser_page.inner_text("#my-apps-body")


@case("ST-04-N3", "FR-03", "브라우저 E2E: 대시보드 → 신청 화면 → 신청 → 대시보드 최근 신청 반영",
      "'+ CAVP 시험 신청' 클릭으로 이동, 신청 후 대시보드 최근 신청·진행중 KPI 에 반영", "positive")
def test_dashboard_to_apply_flow(srv, browser_page):
    app, base = srv
    new_user(app, "apply_flow")
    login(browser_page, base, "apply_flow")
    browser_page.click("#new-app")
    browser_page.wait_for_url("**/cavp/apply")
    browser_page.wait_for_selector("#algorithm option[value='SHA-3']", state="attached")
    browser_page.select_option("#algorithm", "SHA-3"); browser_page.click("#submit-app")
    browser_page.wait_for_function("document.getElementById('my-apps-body').innerText.includes('SHA-3')")
    browser_page.click("a[href='/dashboard']")
    browser_page.wait_for_url("**/dashboard")
    browser_page.wait_for_function("document.getElementById('kpi-in-progress').textContent.trim() === '1'")
    assert "SHA-3" in browser_page.inner_text("#recent-body")
    shot(browser_page, "sc04_3_flow")


@case("ST-04-N4", "FR-03", "브라우저 E2E: 로그인하지 않고 신청 화면에 접근", "로그인 화면으로 이동", "security")
def test_apply_requires_login(srv, browser_page):
    _, base = srv
    browser_page.goto(base + "/cavp/apply")
    browser_page.wait_for_selector("#username")
    assert browser_page.url.rstrip("/") == base
