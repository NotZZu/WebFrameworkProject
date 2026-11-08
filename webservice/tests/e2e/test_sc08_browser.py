"""시스템시험 ST-08 (브라우저 E2E) — SC-05 진행상태 화면의 신청 취소. Playwright 필요(없으면 건너뜀)."""
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


def login(pg, base, username, user_type="individual"):
    pg.goto(base + "/")
    pg.click(f"#tabs button[data-type='{user_type}']")
    pg.fill("#username", username); pg.fill("#password", factories.DEFAULT_PASSWORD)
    pg.click("#submit")
    pg.wait_for_url("**/dashboard")


def setup(app, name, algo="AES", status="submitted", user_type="individual"):
    s = app.session_factory()
    u = factories.make_user(s, username=name, user_type=user_type)
    a = factories.make_application(s, u, algo, status) if user_type == "individual" else None
    s.close()
    return a.id if a else None


def open_status(pg, base, app_id):
    pg.goto(base + "/cavp/status")
    pg.wait_for_selector(f"#apps-body tr[data-id='{app_id}']")
    pg.click(f"#apps-body tr[data-id='{app_id}']")
    pg.wait_for_selector("#detail-body:not([hidden])")


@case("ST-08", "FR-03", "브라우저 E2E: 접수 대기 신청을 확인 단계를 거쳐 취소",
      "'신청 취소' → '취소 확정' 후 상태 '취소', 취소 버튼 사라짐, 목록 배지 '취소', 필터 '취소'에 조회")
def test_cancel_success(srv, browser_page):
    app, base = srv
    app_id = setup(app, "cancel_ok")
    login(browser_page, base, "cancel_ok")
    open_status(browser_page, base, app_id)
    assert browser_page.is_visible("#act-cancel")
    browser_page.click("#act-cancel")
    assert browser_page.is_visible("#cancel-confirm") and not browser_page.is_visible("#act-cancel")
    shot(browser_page, "sc08_1_confirm")
    browser_page.click("#act-cancel-yes")
    browser_page.wait_for_function("document.getElementById('detail-status').textContent === '취소'")
    assert "취소했습니다" in browser_page.inner_text("#detail-msg")
    assert not browser_page.is_visible("#act-cancel") and not browser_page.is_visible("#cancel-confirm")
    assert "취소" in browser_page.inner_text(f"#apps-body tr[data-id='{app_id}']")
    browser_page.select_option("#status-filter", "cancelled")
    browser_page.wait_for_function("document.getElementById('total-count').textContent.includes('총 1건')")
    shot(browser_page, "sc08_2_cancelled")


@case("ST-08-N1", "FR-03", "브라우저 E2E: 확인 단계에서 '돌아가기'", "신청은 접수 대기 그대로, 서버에 취소 요청을 보내지 않음", "negative")
def test_cancel_back_out(srv, browser_page):
    app, base = srv
    app_id = setup(app, "cancel_back")
    login(browser_page, base, "cancel_back")
    open_status(browser_page, base, app_id)
    posts = []
    browser_page.on("request", lambda r: posts.append(r) if r.method == "POST" else None)
    browser_page.click("#act-cancel"); browser_page.click("#act-cancel-no")
    assert browser_page.is_visible("#act-cancel") and not browser_page.is_visible("#cancel-confirm")
    assert browser_page.inner_text("#detail-status") == "접수 대기" and posts == []


@case("ST-08-N2", "FR-03", "브라우저 E2E: 심사 중 신청에는 취소 버튼이 없음", "'신청 취소' 버튼 미표시", "negative")
def test_no_cancel_button_when_reviewing(srv, browser_page):
    app, base = srv
    app_id = setup(app, "cancel_rev", "RSA", "reviewing")
    login(browser_page, base, "cancel_rev")
    open_status(browser_page, base, app_id)
    assert not browser_page.is_visible("#act-cancel")


@case("ST-08-N3", "FR-03", "브라우저 E2E: 취소 확정 직전에 기관이 심사를 시작", "오류 안내 표시, 상태는 '시험 진행중'으로 갱신, 취소 버튼 사라짐", "negative")
def test_cancel_after_review_started(srv, browser_page):
    app, base = srv
    app_id = setup(app, "cancel_race", "SHA-3")
    login(browser_page, base, "cancel_race")
    open_status(browser_page, base, app_id)
    browser_page.click("#act-cancel")
    s = app.session_factory()
    from app.models import CavpApplication
    s.get(CavpApplication, app_id).status = "reviewing"; s.commit(); s.close()
    browser_page.click("#act-cancel-yes")
    browser_page.wait_for_function("document.getElementById('detail-status').textContent === '시험 진행중'")
    assert "취소할 수 없습니다" in browser_page.inner_text("#detail-msg")
    assert not browser_page.is_visible("#act-cancel")
    shot(browser_page, "sc08_3_race")


@case("ST-08-N4", "FR-03", "브라우저 E2E: 기관 계정에는 취소 버튼이 없음", "기관 화면에 '신청 취소' 버튼 요소 없음", "security")
def test_institution_has_no_cancel(srv, browser_page):
    app, base = srv
    owner_app = setup(app, "cancel_owner", "HMAC")
    setup(app, "cancel_officer", user_type="institution")
    login(browser_page, base, "cancel_officer", "institution")
    open_status(browser_page, base, owner_app)
    assert browser_page.locator("#act-cancel").count() == 0
