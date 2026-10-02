"""시스템시험 ST-01 (브라우저 E2E) — SC-01 회원가입/로그인 화면. Playwright 필요(없으면 건너뜀).

실행: pip install playwright && playwright install chromium && pytest tests/e2e
"""
import os
import pathlib
import socket
import threading

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
from werkzeug.serving import make_server  # noqa: E402

from app import create_app  # noqa: E402
from tests.case_registry import case  # noqa: E402


@pytest.fixture(scope="module")
def base_url():
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite://", "SECRET_KEY": "e2e"})
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = make_server("127.0.0.1", port, app, threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


@pytest.fixture()
def page(base_url):
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            pytest.skip("Chromium 실행 불가")
        pg = browser.new_page()
        pg.goto(base_url + "/")
        yield pg
        browser.close()


ART = pathlib.Path(os.environ.get("E2E_ARTIFACT_DIR", "test-artifacts"))


def shot(pg, name):
    ART.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(ART / f"{name}.png"))


def signup(pg, user, pw="Passw0rd1", utype="individual", org=None):
    pg.click("#switch")
    pg.click(f"[data-type={utype}]")
    pg.fill("#username", user); pg.fill("#password", pw); pg.fill("#password2", pw)
    if org:
        pg.fill("#org_code", org)
    pg.click("#submit")


@case("ST-01", "FR-01", "브라우저 E2E: 가입 → 로그인 → 환영 화면 → 로그아웃", "가입 완료 메시지 후 로그인하면 /dashboard 에 사용자명 표시, 로그아웃하면 로그인 화면 복귀", "positive")
def test_signup_login_logout_flow(page, base_url):
    shot(page, "sc01_1_login")
    signup(page, "e2e_user")
    shot(page, "sc01_2_signup")
    page.wait_for_selector(".ok")
    page.fill("#username", "e2e_user"); page.fill("#password", "Passw0rd1"); page.click("#submit")
    page.wait_for_url("**/dashboard")
    assert "e2e_user" in page.inner_text("#welcome")
    shot(page, "sc01_3_after_login")
    page.click("#logout")
    page.wait_for_url(base_url + "/")


@case("ST-01-N1", "FR-01", "브라우저 E2E: 잘못된 비밀번호/약한 비밀번호/불일치 확인", "각각 오류 문구가 표시되고 화면 이동 없음", "negative")
def test_error_messages(page, base_url):
    page.fill("#username", "nobody01"); page.fill("#password", "Wrong0000"); page.click("#submit")
    page.wait_for_function("document.getElementById('msg').textContent.length>0")
    assert "올바르지 않" in page.inner_text("#msg") and page.url == base_url + "/"
    shot(page, "sc01_4_login_error")
    page.click("#switch")
    page.fill("#username", "weakuser1"); page.fill("#password", "12345678"); page.fill("#password2", "12345678"); page.click("#submit")
    page.wait_for_function("document.getElementById('msg').textContent.includes('비밀번호')")
    page.fill("#password", "Passw0rd1"); page.fill("#password2", "Different1"); page.click("#submit")
    assert "일치하지" in page.inner_text("#msg")


@case("ST-01-N2", "FR-01", "브라우저 E2E: 비로그인으로 /dashboard 접근, 유형 탭 불일치 로그인", "로그인 화면으로 리다이렉트 / 유형 불일치 오류 표시", "security")
def test_guard_and_type_mismatch(page, base_url):
    page.goto(base_url + "/dashboard")
    assert page.url == base_url + "/"
    signup(page, "corp_user", utype="company", org="ORG-1")
    page.wait_for_selector(".ok")
    page.click("[data-type=individual]")
    page.fill("#username", "corp_user"); page.fill("#password", "Passw0rd1"); page.click("#submit")
    page.wait_for_function("document.getElementById('msg').textContent.includes('유형')")
    assert page.url == base_url + "/"
