"""공격(결함 탐색) 시험 — SC-03 가명·익명정보 처리.

개인정보를 다루는 화면이므로 '원본이 어디에도 남지 않는가', '남의 것을 건드릴 수 있는가', '이상한 입력에 서버가 죽는가'를 본다.
각 시험은 안전하게 동작해야 하는 쪽을 단언한다(실패하면 곧 결함).
"""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select, text

from app import create_app
from app.models import PersonalInfo
from tests import factories
from tests.case_registry import case
from tests.integration.conftest import login

BODY = {"mode": "pseudonym", "name": "홍길동", "birthdate": "1990-04-12"}


def dump_all(db):
    out = ""
    for (t,) in db.execute(text("SELECT name FROM sqlite_master WHERE type='table'")):
        out += str(db.execute(text(f"SELECT * FROM {t}")).fetchall())
    return out


def n_rows(db):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(PersonalInfo))


@case("IT-ATK-31", "FR-02", "로그인하지 않고 가명 처리·조회 호출", "두 API 모두 401, personal_info 0건", "security")
def test_requires_login(client, db):
    assert client.post("/api/privacy/process", json=BODY).status_code == 401
    assert client.get("/api/privacy/me").status_code == 401
    assert n_rows(db) == 0


@case("IT-ATK-32", "FR-02", "요청에 user_id·pseudonym_id 를 끼워 넣어 남의 정보를 덮어쓰거나 ID 를 지정", "무시되고 본인 것만 처리, 지정한 가명 ID 불채택", "security")
def test_mass_assignment_ignored(login_as, db):
    a, ua = login_as(username="usera01")
    b, ub = login_as(username="userb01")
    b.post("/api/privacy/process", json=BODY)
    before = b.get("/api/privacy/me").get_json()
    r = a.post("/api/privacy/process", json={**BODY, "name": "김철수", "user_id": ub.id, "pseudonym_id": "PSN-0000000000000000",
                                              "level": "anonymous", "masked_display_value": "해킹"})
    assert r.status_code == 200 and r.get_json()["pseudonym_id"] != "PSN-0000000000000000"
    assert b.get("/api/privacy/me").get_json() == before
    assert a.get("/api/privacy/me").get_json()["display"].startswith("김*수")


@case("IT-ATK-33", "FR-02", "이름·생년월일·모드에 엉뚱한 자료형(숫자·목록·객체·null·참거짓)", "모두 400 (500 아님), 저장 0건", "negative")
@pytest.mark.parametrize("over", [{"name": 123}, {"name": ["홍길동"]}, {"name": {"a": 1}}, {"name": True},
                                  {"birthdate": 19900412}, {"birthdate": ["1990-04-12"]}, {"birthdate": None},
                                  {"mode": ["pseudonym"]}, {"mode": 1}, {"mode": {"x": 1}}])
def test_wrong_types_are_400(login_as, db, over):
    c, _ = login_as()
    r = c.post("/api/privacy/process", json={**BODY, **over})
    assert r.status_code == 400
    assert n_rows(db) == 0


@case("IT-ATK-34", "FR-02", "생년월일의 다른 표기(주차·점·슬래시·시간 포함·전각 숫자·공백)", "YYYY-MM-DD 가 아니면 400", "negative")
@pytest.mark.parametrize("raw", ["1990-W15-1", "19900412", "1990.04.12", "1990/04/12", "1990-04-12T00:00:00",
                                 " 1990-04-12", "1990-04-12 ", "１９９０-０４-１２", "0000-00-00", "1990-02-30"])
def test_birthdate_formats(login_as, db, raw):
    c, _ = login_as()
    assert c.post("/api/privacy/process", json={**BODY, "birthdate": raw}).status_code == 400
    assert n_rows(db) == 0


@case("IT-ATK-35", "FR-02", "이름에 제어문자·줄바꿈·NUL·제로폭 문자·과도한 길이", "400, 저장 0건 (로그·CSV 주입 차단)", "security")
@pytest.mark.parametrize("name", ["홍\n길동", "홍길\r\n동", "홍\x00길동", "홍​길동", "홍‮길동", "가" * 51, "가" * 100000])
def test_name_control_chars_and_length(login_as, db, name):
    c, _ = login_as()
    r = c.post("/api/privacy/process", json={**BODY, "name": name})
    assert r.status_code in (400, 413)
    assert n_rows(db) == 0


@case("IT-ATK-36", "FR-02", "오류 응답에 입력한 이름·생년월일이 되돌아오는지(반사)", "오류 메시지에 원본 값 없음", "security")
def test_errors_do_not_echo_input(login_as):
    c, _ = login_as()
    secret_name = "비밀이름\n"
    for body in ({**BODY, "name": secret_name}, {**BODY, "birthdate": "2999-12-31"}, {**BODY, "birthdate": "9999-99-99"},
                 {**BODY, "mode": "홍길동모드"}):
        text_ = c.post("/api/privacy/process", json=body).get_data(as_text=True)
        assert "비밀이름" not in text_ and "2999" not in text_ and "9999" not in text_ and "홍길동모드" not in text_


@case("IT-ATK-37", "FR-02", "이름에 HTML·스크립트·SQL 조각을 넣어 저장·반환", "마스킹된 값만 저장되고 JSON 으로만 응답, 테이블 정상", "security")
@pytest.mark.parametrize("name", ["<script>alert(1)</script>", "'; DROP TABLE personal_info;--", "홍길동</td><td>"])
def test_markup_and_sql_in_name(login_as, db, name):
    c, _ = login_as()
    r = c.post("/api/privacy/process", json={**BODY, "name": name[:50]})
    assert r.status_code == 200 and r.mimetype == "application/json"
    assert name[1:-1] not in dump_all(db) and n_rows(db) == 1


@case("IT-ATK-38", "FR-02", "같은 사용자가 가명 처리를 동시에 여러 번 호출", "행 1건, 모든 응답의 가명 ID 가 같음", "security")
def test_concurrent_process_single_row(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "t" * 32, "DATABASE_URL": f"sqlite:///{tmp_path}/p.db",
                      "CERT_STORAGE_DIR": str(tmp_path)})
    s = app.session_factory(); u = factories.make_user(s, username="racer_priv"); s.close()
    cookies = []
    for _ in range(8):
        c = app.test_client(); assert login(c, u.username).status_code == 200; cookies.append(c)

    def job(i):
        return cookies[i].post("/api/privacy/process", json=BODY).status_code, cookies[i].get("/api/privacy/me").get_json()
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(job, range(8)))
    assert {r[0] for r in res} == {200}, res
    s = app.session_factory()
    assert s.scalar(select(func.count()).select_from(PersonalInfo)) == 1
    assert len({r[1]["pseudonym_id"] for r in res}) == 1
    s.close()


@case("IT-ATK-39", "FR-02", "가명 ID 가 추측 가능한지(많은 사용자 발급값의 유일성·형식)", "서로 다른 사용자 200명의 ID 가 모두 유일", "security")
def test_pseudonym_ids_unique_across_users(app, db):
    c = app.test_client()
    ids = set()
    for i in range(200):
        u = factories.make_user(db, username=f"bulk{i:04d}")
        assert login(c, u.username).status_code == 200
        ids.add(c.post("/api/privacy/process", json=BODY).get_json()["pseudonym_id"])
    assert len(ids) == 200


@case("IT-ATK-40", "FR-02", "로그아웃한 쿠키로 처리 결과 조회·재처리", "401, 기존 결과 변경 없음", "security")
def test_old_cookie_cannot_access(login_as, db):
    c, _ = login_as()
    c.post("/api/privacy/process", json=BODY)
    stolen = c.get_cookie("session")
    assert stolen is not None
    c.post("/api/auth/logout")
    thief = c.application.test_client()
    thief.set_cookie("session", stolen.value)
    assert thief.get("/api/privacy/me").status_code == 401
    assert thief.post("/api/privacy/process", json={**BODY, "mode": "anonymous"}).status_code == 401
    assert db.scalar(select(PersonalInfo.anonymization_level)) == "pseudonym"


@case("IT-ATK-41", "FR-02", "본문이 JSON 이 아니거나 거대/중첩된 요청", "400/413, 서버 오류 없음", "negative")
def test_bad_bodies(login_as):
    c, _ = login_as()
    for data, ctype in ((b"not json", "application/json"), (b"[1,2]", "application/json"), (b"", "application/json"),
                        (json.dumps({"mode": "pseudonym", "name": "가" * 70000, "birthdate": "1990-04-12"}).encode(), "application/json"),
                        (b"[" * 5000 + b"]" * 5000, "application/json")):
        r = c.post("/api/privacy/process", data=data, content_type=ctype)
        assert r.status_code in (400, 413), (data[:20], r.status_code)
