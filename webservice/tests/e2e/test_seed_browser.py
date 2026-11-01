"""시스템시험 ST-SEED (브라우저 E2E) — 초기 데이터 적재 후 데모 계정으로 화면 확인. Playwright 필요(없으면 건너뜀)."""
import os
import pathlib
import socket
import threading

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
from werkzeug.serving import make_server  # noqa: E402

from app import create_app  # noqa: E402
from app.seed import seed  # noqa: E402
from tests.case_registry import case  # noqa: E402

ART = pathlib.Path(os.environ.get("E2E_ARTIFACT_DIR", "test-artifacts"))


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    store = tmp_path_factory.mktemp("seedcerts")
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite://", "SECRET_KEY": "e2e",
                      "CERT_STORAGE_DIR": str(store)})
    st = app.store_factory(); seed(st, str(store)); st.close()
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture()
def pg():
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            pytest.skip("Chromium 실행 불가")
        yield browser.new_page(viewport={"width": 1280, "height": 800})
        browser.close()


def login(pg, base, username, user_type):
    pg.goto(base + "/")
    pg.click(f"#tabs button[data-type='{user_type}']")
    pg.fill("#username", username); pg.fill("#password", "Demo1234")
    pg.click("#submit")
    pg.wait_for_url("**/dashboard")


@case("ST-SEED", "FR-04", "브라우저 E2E: 시드 적재 후 기관 데모 계정의 위변조 탐지 화면에 의심 1건", "전체 3, 정상 2, 의심 1, 의심 행 강조")
def test_seeded_tamper_screen(srv, pg):
    login(pg, srv, "demo_institution", "institution")
    pg.goto(srv + "/tamper")
    pg.wait_for_function("document.querySelectorAll('#tamper-body tr.item').length === 3")
    assert pg.inner_text("#kpi-total").strip() == "3"
    assert pg.inner_text("#kpi-suspected").strip() == "1" and pg.inner_text("#kpi-normal").strip() == "2"
    pg.click("#verify-all")
    pg.wait_for_function("document.getElementById('tamper-msg').innerText.includes('검증 완료')")
    assert "1건" in pg.inner_text("#tamper-msg")
    ART.mkdir(parents=True, exist_ok=True); pg.screenshot(path=str(ART / "seed_1_tamper.png"))


@case("ST-SEED-N1", "FR-03", "브라우저 E2E: 개인 데모 계정은 본인 신청 3건만 보임", "신청 목록 3건, 타인(기업) 신청 미표시", "negative")
def test_seeded_individual_scope(srv, pg):
    login(pg, srv, "demo_individual", "individual")
    pg.goto(srv + "/cavp/status")
    pg.wait_for_function("document.querySelectorAll('#apps-body tr.item').length === 3")
    assert "demo_company" not in pg.inner_text("#apps-body")
