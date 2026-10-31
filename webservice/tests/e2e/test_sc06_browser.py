"""시스템시험 ST-06/ST-07 (브라우저 E2E) — SC-06 검증서 이력 조회, SC-07 위변조 탐지 결과. Playwright 필요(없으면 건너뜀)."""
import os
import pathlib
import socket
import threading

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
from werkzeug.serving import make_server  # noqa: E402

from app import create_app  # noqa: E402
from app.services import certificate_service  # noqa: E402
from tests import factories  # noqa: E402
from tests.case_registry import case  # noqa: E402

ART = pathlib.Path(os.environ.get("E2E_ARTIFACT_DIR", "test-artifacts"))


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    store = tmp_path_factory.mktemp("certs")
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite://", "SECRET_KEY": "e2e",
                      "CERT_STORAGE_DIR": str(store)})
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield app, f"http://127.0.0.1:{port}", store
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


def issue(app, officer, owner, algo="AES", content=b"cert-body"):
    s = app.session_factory()
    a = factories.make_application(s, owner, algo, "approved")
    c = certificate_service.issue_certificate(s, officer.id, a.id, "CAVP", content, app.config["CERT_STORAGE_DIR"])
    cid = c.id; s.close()
    return cid


def world(app, owner_name, officer_name):
    s = app.session_factory()
    owner = factories.make_user(s, username=owner_name)
    officer = factories.make_user(s, username=officer_name, user_type="institution")
    s.expunge_all(); s.close()
    return owner, officer


@case("ST-06", "FR-04", "브라우저 E2E: 내 검증서 이력이 최신순으로 표시되고 행을 누르면 상세", "2건 표시, 상세에 정상 배지, 해시·경로 미노출")
def test_history_and_detail(srv, browser_page):
    app, base, _ = srv
    owner, officer = world(app, "st6_owner", "st6_officer")
    issue(app, officer, owner, "AES"); issue(app, officer, owner, "RSA")
    login(browser_page, base, "st6_owner")
    browser_page.goto(base + "/certificates")
    browser_page.wait_for_function("document.querySelectorAll('#certs-body tr.item').length === 2")
    browser_page.click("#certs-body tr.item")
    browser_page.wait_for_selector("#cert-detail-panel:not([hidden])")
    txt = browser_page.inner_text("#cert-detail")
    assert "정상" in txt and "integrity" not in txt.lower() and ".bin" not in txt
    assert browser_page.locator("#issue-panel").count() == 0 or not browser_page.locator("#issue-panel").is_visible()
    shot(browser_page, "sc06_1_history")


@case("ST-06-N1", "FR-04", "브라우저 E2E: 타인의 검증서는 목록에 나타나지 않음", "다른 사용자 계정으로 접속하면 0건", "negative")
def test_stranger_isolation(srv, browser_page):
    app, base, _ = srv
    owner, officer = world(app, "st6_o2", "st6_off2")
    issue(app, officer, owner)
    s = app.session_factory(); factories.make_user(s, username="st6_stranger"); s.close()
    login(browser_page, base, "st6_stranger")
    browser_page.goto(base + "/certificates")
    browser_page.wait_for_timeout(800)
    assert browser_page.locator("#certs-body tr.item").count() == 0


@case("ST-06-N2", "FR-04", "브라우저 E2E: 로그인하지 않으면 이력·탐지 화면이 로그인으로 이동", "/certificates, /tamper 모두 로그인 화면", "negative")
def test_login_redirect(srv, browser_page):
    _, base, _ = srv
    for path in ("/certificates", "/tamper"):
        browser_page.goto(base + path)
        assert browser_page.url.rstrip("/") == base


@case("ST-06-N3", "FR-04", "브라우저 E2E: 기관 사용자가 승인된 신청에 검증서를 발급", "발급 후 이력에 1건 추가, 성공 메시지", "")
def test_institution_issue(srv, browser_page):
    app, base, _ = srv
    owner, officer = world(app, "st6_o3", "st6_off3")
    s = app.session_factory(); a = factories.make_application(s, owner, "SHA-2", "approved"); aid = a.id; s.close()
    login(browser_page, base, "st6_off3", "institution")
    browser_page.goto(base + "/certificates")
    browser_page.wait_for_selector("#issue-panel")
    browser_page.wait_for_function("document.querySelectorAll('#issue-app option').length > 1")
    browser_page.select_option("#issue-app", str(aid))
    browser_page.fill("#issue-content", "시험 결과 본문")
    browser_page.click("#issue-submit")
    browser_page.wait_for_function("document.getElementById('issue-msg').innerText.trim() !== ''")
    browser_page.wait_for_function("document.querySelectorAll('#certs-body tr.item').length >= 1")
    assert "발급" in browser_page.inner_text("#issue-msg")
    shot(browser_page, "sc06_2_issue")


@case("ST-07", "FR-05", "브라우저 E2E: 검증서 파일이 바뀌면 개별 검증에서 '위변조 의심'으로 표시", "변조 전 정상, 변조 후 검증하면 의심 표시와 요약 수치 갱신")
def test_tamper_detection(srv, browser_page):
    app, base, store = srv
    owner, officer = world(app, "st7_owner", "st7_officer")
    cid = issue(app, officer, owner, "ECDSA", b"original")
    issue(app, officer, owner, "AES", b"fine")
    login(browser_page, base, "st7_owner")
    browser_page.goto(base + "/tamper")
    browser_page.wait_for_function("document.querySelectorAll('#tamper-body tr.item').length === 2")
    assert browser_page.inner_text("#kpi-suspected").strip() == "0"
    (pathlib.Path(store) / f"cert_{cid}.bin").write_bytes(b"forged")
    browser_page.click(f"#tamper-body button.verify[data-id='{cid}']")
    browser_page.wait_for_function("document.getElementById('kpi-suspected').innerText.trim() === '1'")
    assert "위변조 의심" in browser_page.inner_text("#tamper-body")
    shot(browser_page, "sc07_1_tamper")


@case("ST-07-N1", "FR-05", "브라우저 E2E: 전체 검증 버튼이 현재 목록을 모두 검사", "변조 1건 포함 시 '의심 1건' 메시지", "boundary")
def test_verify_all(srv, browser_page):
    app, base, store = srv
    owner, officer = world(app, "st7_o2", "st7_off2")
    cid = issue(app, officer, owner, "AES", b"a"); issue(app, officer, owner, "RSA", b"b")
    (pathlib.Path(store) / f"cert_{cid}.bin").write_bytes(b"tampered")
    login(browser_page, base, "st7_o2")
    browser_page.goto(base + "/tamper")
    browser_page.wait_for_function("document.querySelectorAll('#tamper-body tr.item').length === 2")
    browser_page.click("#verify-all")
    browser_page.wait_for_function("document.getElementById('tamper-msg').innerText.includes('검증 완료')")
    assert "1건" in browser_page.inner_text("#tamper-msg")
    shot(browser_page, "sc07_2_verify_all")
