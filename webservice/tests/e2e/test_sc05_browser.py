"""시스템시험 ST-05 (브라우저 E2E) — SC-05 CAVP 진행상태 조회·심사 화면. Playwright 필요(없으면 건너뜀)."""
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


def rows(pg):
    return pg.locator("#apps-body tr.item").count()


@case("ST-05", "FR-03", "브라우저 E2E: 내 신청 목록에 상태 배지가 보이고 상태 필터로 좁혀짐",
      "3건 표시, 필터 '시험 완료' 선택 시 1건, '전체'로 돌아오면 3건")
def test_list_and_filter(srv, browser_page):
    app, base = srv
    s = app.session_factory(); u = factories.make_user(s, username="st5_list")
    factories.make_application(s, u, "AES", "approved")
    factories.make_application(s, u, "RSA", "reviewing")
    factories.make_application(s, u, "HMAC", "submitted"); s.close()
    login(browser_page, base, "st5_list")
    browser_page.goto(base + "/cavp/status")
    browser_page.wait_for_function("document.querySelectorAll('#apps-body tr.item').length === 3")
    assert "시험 진행중" in browser_page.inner_text("#apps-body")
    browser_page.select_option("#status-filter", "approved")
    browser_page.wait_for_function("document.querySelectorAll('#apps-body tr.item').length === 1")
    assert "AES" in browser_page.inner_text("#apps-body")
    browser_page.select_option("#status-filter", "")
    browser_page.wait_for_function("document.querySelectorAll('#apps-body tr.item').length === 3")
    shot(browser_page, "sc05_1_list")


@case("ST-05-N1", "FR-03", "브라우저 E2E: 신청 행을 누르면 진행 단계 상세가 표시", "현재 단계가 강조되고, 일반 사용자에게는 심사 버튼이 없음")
def test_detail_steps(srv, browser_page):
    app, base = srv
    s = app.session_factory(); u = factories.make_user(s, username="st5_detail")
    factories.make_application(s, u, "SHA-2", "reviewing"); s.close()
    login(browser_page, base, "st5_detail")
    browser_page.goto(base + "/cavp/status")
    browser_page.wait_for_selector("#apps-body tr.item")
    browser_page.click("#apps-body tr.item")
    browser_page.wait_for_selector("#detail .step.now")
    assert "심사" in browser_page.inner_text("#detail .step.now")
    assert "SHA-2" in browser_page.inner_text("#detail")
    assert browser_page.locator("#act-approve").count() == 0 or not browser_page.locator("#act-approve").is_visible()
    shot(browser_page, "sc05_2_detail")


@case("ST-05-N2", "FR-03", "브라우저 E2E: 신청이 많으면 페이지로 나뉘어 이동", "12건 중 1페이지 10건, 다음 누르면 2건, 이전 누르면 10건", "boundary")
def test_pagination(srv, browser_page):
    app, base = srv
    s = app.session_factory(); u = factories.make_user(s, username="st5_page")
    for _ in range(12):
        factories.make_application(s, u, "AES", "approved")
    s.close()
    login(browser_page, base, "st5_page")
    browser_page.goto(base + "/cavp/status")
    browser_page.wait_for_function("document.querySelectorAll('#apps-body tr.item').length === 10")
    assert "1 / 2" in browser_page.inner_text("#page-info")
    browser_page.click("#next")
    browser_page.wait_for_function("document.querySelectorAll('#apps-body tr.item').length === 2")
    assert "2 / 2" in browser_page.inner_text("#page-info")
    assert browser_page.locator("#next").is_disabled()
    browser_page.click("#prev")
    browser_page.wait_for_function("document.querySelectorAll('#apps-body tr.item').length === 10")


@case("ST-05-N3", "FR-03", "브라우저 E2E: 기관 사용자가 신청을 심사 시작 → 승인", "타인 신청이 보이고, 심사 시작 후 '시험 진행중', 승인 후 '시험 완료'이며 버튼이 사라짐")
def test_institution_review_flow(srv, browser_page):
    app, base = srv
    s = app.session_factory()
    person = factories.make_user(s, username="st5_person")
    factories.make_user(s, username="st5_officer", user_type="institution")
    factories.make_application(s, person, "ECDSA", "submitted"); s.close()
    login(browser_page, base, "st5_officer", "institution")
    browser_page.goto(base + "/cavp/status")
    browser_page.wait_for_selector("#apps-body tr.item")
    assert "st5_person" in browser_page.inner_text("#apps-body")
    browser_page.click("#apps-body tr.item")
    browser_page.wait_for_selector("#act-review")
    assert not browser_page.locator("#act-approve").is_visible()
    browser_page.click("#act-review")
    browser_page.wait_for_selector("#act-approve", state="visible")
    assert "시험 진행중" in browser_page.inner_text("#detail-status")
    browser_page.click("#act-approve")
    browser_page.wait_for_function("document.getElementById('detail-status').innerText.includes('시험 완료')")
    assert not browser_page.locator("#act-approve").is_visible() and not browser_page.locator("#act-reject").is_visible()
    assert "시험 완료" in browser_page.inner_text("#apps-body")
    shot(browser_page, "sc05_3_review")


@case("ST-05-N4", "FR-03", "브라우저 E2E: 기관 사용자가 반려 처리", "심사 시작 후 반려하면 '반려'로 표시되고 버튼이 사라짐", "negative")
def test_institution_reject(srv, browser_page):
    app, base = srv
    s = app.session_factory()
    person = factories.make_user(s, username="st5_p2")
    factories.make_user(s, username="st5_o2", user_type="institution")
    factories.make_application(s, person, "DRBG", "reviewing"); s.close()
    login(browser_page, base, "st5_o2", "institution")
    browser_page.goto(base + "/cavp/status")
    browser_page.wait_for_selector("#apps-body tr.item")
    browser_page.click("#apps-body tr.item")
    browser_page.wait_for_selector("#act-reject", state="visible")
    browser_page.click("#act-reject")
    browser_page.wait_for_function("document.getElementById('detail-status').innerText.includes('반려')")
    assert not browser_page.locator("#act-reject").is_visible()


@case("ST-05-N5", "FR-03", "브라우저 E2E: 신청이 없을 때 빈 상태와 로그인 없이 접근", "빈 안내 표시 / 비로그인은 로그인 화면으로 이동", "negative")
def test_empty_and_auth(srv, browser_page):
    app, base = srv
    s = app.session_factory(); factories.make_user(s, username="st5_empty"); s.close()
    browser_page.goto(base + "/cavp/status")
    browser_page.wait_for_selector("#username")
    login(browser_page, base, "st5_empty")
    browser_page.goto(base + "/cavp/status")
    browser_page.wait_for_selector("#apps-body .empty")
    assert "아직 신청 내역이 없습니다" in browser_page.inner_text("#apps-body")
