"""시스템시험 ST-10 (브라우저 E2E) — 보안 정책(CSP) 적용 상태의 화면 동작과 모바일 폭 레이아웃. Playwright 필요(없으면 건너뜀)."""
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
        yield browser.new_page(viewport={"width": 1280, "height": 800})  # CSP 를 끄지 않은 그대로 실행
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



def collect_errors(pg):
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    return errs


@case("ST-10", "NFR-보안", "브라우저 E2E: CSP 를 끄지 않은 상태에서 로그인과 주요 화면이 동작",
      "로그인 후 대시보드·신청·진행상태 화면이 열리고 데이터가 채워지며, 콘솔에 CSP 위반이나 스크립트 오류가 없음", "security")
def test_pages_work_under_csp(srv, browser_page):
    app, base = srv
    s = app.session_factory(); u = factories.make_user(s, username="csp_user"); factories.make_application(s, u, "AES", "submitted"); s.close()
    errs = collect_errors(browser_page)
    login(browser_page, base, "csp_user")
    browser_page.locator("#kpi-in-progress").filter(has_text="1").wait_for()
    browser_page.goto(base + "/cavp/status")
    browser_page.locator("#apps-body tr.item").first.wait_for()
    browser_page.click("#apps-body tr.item")
    browser_page.locator("#act-cancel").wait_for(state="visible")
    browser_page.goto(base + "/cavp/apply")
    browser_page.locator("#algorithm option[value='RSA']").wait_for(state="attached")
    assert [e for e in errs if "Content Security Policy" in e or "Refused" in e] == []
    assert errs == []
    shot(browser_page, "sc10_1_csp")


@case("ST-10-N1", "NFR-사용성", "브라우저 E2E: 휴대폰 폭(390px)에서 가로 스크롤 없이 표시",
      "로그인·대시보드·신청 현황·관리자 화면에서 문서 가로 길이가 화면 폭 이내", "boundary")
def test_mobile_layout_has_no_horizontal_scroll(srv, browser_page):
    app, base = srv
    s = app.session_factory(); factories.make_user(s, username="mob_officer", user_type="institution"); s.close()
    browser_page.set_viewport_size({"width": 390, "height": 844})
    browser_page.goto(base + "/")
    assert browser_page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    login(browser_page, base, "mob_officer", "institution")
    for path in ("/dashboard", "/cavp/apply", "/cavp/status", "/certificates", "/tamper", "/privacy", "/admin"):
        browser_page.goto(base + path)
        browser_page.wait_for_load_state("networkidle")
        w = browser_page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        assert w[0] <= w[1], (path, w)
    shot(browser_page, "sc10_2_mobile")
