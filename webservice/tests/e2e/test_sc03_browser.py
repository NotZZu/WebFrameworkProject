"""시스템시험 ST-03 (브라우저 E2E) — SC-03 가명·익명정보 처리 화면. Playwright 필요(없으면 건너뜀)."""
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


def fill(pg, name, birth):
    pg.fill("#name", name)
    pg.fill("#birthdate", birth)


@case("ST-03", "FR-02", "브라우저 E2E: 가명 처리 → 마스킹된 결과와 가명 ID 표시, 입력 원본은 화면에서 사라짐",
      "표시값 '홍*동 (…대)', 가명 ID 'PSN-…', 이름·생년월일 입력칸 비워짐, 페이지 어디에도 '홍길동' 없음", "positive")
def test_pseudonym_flow(srv, browser_page):
    app, base = srv
    s = app.session_factory(); factories.make_user(s, username="st3_pseudo"); s.close()
    login(browser_page, base, "st3_pseudo")
    browser_page.goto(base + "/privacy")
    assert "아직 처리한 내용이 없습니다" in browser_page.inner_text("#result-empty")
    fill(browser_page, "홍길동", "1990-04-12")
    browser_page.click("#submit-privacy")
    browser_page.wait_for_selector("#result:not([hidden])")
    assert browser_page.inner_text("#result-display").startswith("홍*동 (")
    assert browser_page.inner_text("#result-pid").startswith("PSN-")
    assert browser_page.input_value("#name") == "" and browser_page.input_value("#birthdate") == ""
    assert "홍길동" not in browser_page.inner_text("body")  # 입력칸 안내문구(placeholder)는 화면 글자가 아님
    shot(browser_page, "sc03_1_pseudonym")
    browser_page.reload()   # 새로고침해도 저장된 결과가 다시 보임
    browser_page.wait_for_selector("#result:not([hidden])")
    assert browser_page.inner_text("#result-display").startswith("홍*동 (")


@case("ST-03-N1", "FR-02", "브라우저 E2E: 익명으로 다시 처리하면 가명 ID 가 사라진다", "표시값 '익명', 가명 ID '없음 (익명)'")
def test_switch_to_anonymous(srv, browser_page):
    app, base = srv
    s = app.session_factory(); factories.make_user(s, username="st3_anon"); s.close()
    login(browser_page, base, "st3_anon")
    browser_page.goto(base + "/privacy")
    fill(browser_page, "김철수", "1985-01-01")
    browser_page.click("#submit-privacy")
    browser_page.wait_for_selector("#result:not([hidden])")
    first = browser_page.inner_text("#result-pid")
    browser_page.check("#mode-anonymous")
    fill(browser_page, "김철수", "1985-01-01")
    browser_page.click("#submit-privacy")
    browser_page.wait_for_function("document.getElementById('result-display').textContent === '익명'")
    assert "없음" in browser_page.inner_text("#result-pid") and first.startswith("PSN-")
    shot(browser_page, "sc03_2_anonymous")


@case("ST-03-N2", "FR-02", "브라우저 E2E: 입력 누락·미래 날짜 안내", "이름/생년월일 누락 시 안내 문구, 미래 날짜는 서버 오류 안내, 결과 영역은 그대로", "negative")
def test_validation_messages(srv, browser_page):
    app, base = srv
    s = app.session_factory(); factories.make_user(s, username="st3_valid"); s.close()
    login(browser_page, base, "st3_valid")
    browser_page.goto(base + "/privacy")
    browser_page.click("#submit-privacy")
    assert "이름" in browser_page.inner_text("#privacy-msg")
    browser_page.fill("#name", "홍길동")
    browser_page.click("#submit-privacy")
    assert "생년월일" in browser_page.inner_text("#privacy-msg")
    fill(browser_page, "홍길동", "2999-01-01")
    browser_page.click("#submit-privacy")
    browser_page.wait_for_function("document.getElementById('privacy-msg').className === 'err' && document.getElementById('privacy-msg').textContent.includes('생년월일')")
    assert browser_page.locator("#result").is_hidden()
    assert "2999" not in browser_page.inner_text("#privacy-msg")


@case("ST-03-N3", "FR-02", "브라우저 E2E: 이름에 HTML 을 넣어도 화면에 요소가 생기지 않음(XSS)", "결과는 글자로만 표시, 삽입된 img 요소 없음, 경고창 없음", "security")
def test_html_name_is_text(srv, browser_page):
    app, base = srv
    s = app.session_factory(); factories.make_user(s, username="st3_xss"); s.close()
    dialogs = []
    browser_page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    login(browser_page, base, "st3_xss")
    browser_page.goto(base + "/privacy")
    fill(browser_page, "<img src=x onerror=alert(1)>", "1990-04-12")
    browser_page.click("#submit-privacy")
    browser_page.wait_for_selector("#result:not([hidden])")
    assert browser_page.locator("#result img").count() == 0 and dialogs == []
    assert "onerror" not in browser_page.inner_text("#result-display")


@case("ST-03-N4", "FR-02", "브라우저 E2E: 로그인하지 않고 접근하면 로그인 화면으로", "/privacy → 로그인 화면(/)", "security")
def test_requires_login(srv, browser_page):
    _, base = srv
    browser_page.goto(base + "/privacy")
    assert browser_page.url.rstrip("/") == base
    assert browser_page.locator("#username").count() == 1
