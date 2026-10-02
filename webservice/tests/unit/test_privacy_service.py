"""단위시험 UT-PRIV — FR-02 가명·익명정보 처리 모의 (PrivacyService)."""
import re
from datetime import date

import pytest
from sqlalchemy import func, select, text

from app.errors import NotFoundError, ValidationError
from app.models import PersonalInfo
from app.services import privacy_service as priv
from tests import factories
from tests.case_registry import case

TODAY = date(2026, 10, 2)


@case("UT-PRIV-01", "FR-02", "issue_pseudonym_id: 형식 'PSN-'+16hex", "정규식 ^PSN-[0-9a-f]{16}$ 일치")
def test_pseudonym_id_format():
    assert re.fullmatch(r"PSN-[0-9a-f]{16}", priv.issue_pseudonym_id())


@case("UT-PRIV-02", "FR-02", "issue_pseudonym_id: 호출마다 다른 값", "1000회 호출 모두 유일")
def test_pseudonym_id_unique():
    assert len({priv.issue_pseudonym_id() for _ in range(1000)}) == 1000


@case("UT-PRIV-03", "FR-02", "mask_name: 길이별 마스킹 규칙", "홍길동→홍*동, 남궁민수→남**수, 홍길→홍*, 홍→*, John→J**n", "boundary")
@pytest.mark.parametrize("raw,masked", [("홍길동", "홍*동"), ("남궁민수", "남**수"), ("홍길", "홍*"), ("홍", "*"), ("John", "J**n")])
def test_mask_name(raw, masked):
    assert priv.mask_name(raw) == masked


@case("UT-PRIV-04", "FR-02", "mask_name: 빈 값/공백만", "ValidationError", "negative")
@pytest.mark.parametrize("raw", ["", "   ", "\t\n", None])
def test_mask_name_empty(raw):
    with pytest.raises(ValidationError):
        priv.mask_name(raw)


@case("UT-PRIV-05", "FR-02", "mask_name: 앞뒤 공백은 제거 후 마스킹", "' 홍길동 ' → '홍*동'", "boundary")
def test_mask_name_strips_whitespace():
    assert priv.mask_name(" 홍길동 ") == "홍*동"


@case("UT-PRIV-06", "FR-02", "mask_phone: 하이픈 유/무 입력", "모두 '010-****-5678'")
@pytest.mark.parametrize("raw", ["010-1234-5678", "01012345678"])
def test_mask_phone(raw):
    assert priv.mask_phone(raw) == "010-****-5678"


@case("UT-PRIV-07", "FR-02", "mask_phone: 3자리 국번 형식(010-123-4567)", "'010-***-4567'", "boundary")
def test_mask_phone_short_middle():
    assert priv.mask_phone("010-123-4567") == "010-***-4567"


@case("UT-PRIV-08", "FR-02", "mask_phone: 형식 오류", "ValidationError", "negative")
@pytest.mark.parametrize("raw", ["", "abc", "010-1234-567", "010-1234-56789", "02-1234-5678", "010 1234 5678 9", None])
def test_mask_phone_invalid(raw):
    with pytest.raises(ValidationError):
        priv.mask_phone(raw)


@case("UT-PRIV-09", "FR-02", "anonymize_birthdate: 대표 연령대", "1990-04-12 → '30대' (기준일 2026-10-02)")
def test_anonymize_birthdate_basic():
    assert priv.anonymize_birthdate(date(1990, 4, 12), TODAY) == "30대"


@case("UT-PRIV-10", "FR-02", "anonymize_birthdate: 생일 전/후 경계(만 나이)", "생일 당일부터 다음 연령대", "boundary")
@pytest.mark.parametrize("birth,expected", [
    (date(1996, 10, 2), "30대"), (date(1996, 10, 3), "20대"),
    (date(2016, 10, 2), "10대"), (date(2016, 10, 3), "10세 미만"),
    (date(2026, 10, 2), "10세 미만"),
    (date(1926, 10, 2), "100세 이상"), (date(1926, 10, 3), "90대"),
])
def test_anonymize_birthdate_boundaries(birth, expected):
    assert priv.anonymize_birthdate(birth, TODAY) == expected


@case("UT-PRIV-11", "FR-02", "anonymize_birthdate: 윤일(2/29) 생일", "평년 2/28 에는 아직 생일 전, 3/1 부터 생일 후", "boundary")
def test_anonymize_birthdate_leap_day():
    assert priv.anonymize_birthdate(date(2000, 2, 29), date(2025, 2, 28)) == "20대"   # 24세
    assert priv.anonymize_birthdate(date(2000, 2, 29), date(2030, 2, 28)) == "20대"   # 29세
    assert priv.anonymize_birthdate(date(2000, 2, 29), date(2030, 3, 1)) == "30대"    # 30세


@case("UT-PRIV-12", "FR-02", "anonymize_birthdate: 미래 날짜", "ValidationError", "negative")
def test_anonymize_birthdate_future():
    with pytest.raises(ValidationError):
        priv.anonymize_birthdate(date(2026, 10, 3), TODAY)


@case("UT-PRIV-13", "FR-02", "anonymize_birthdate: 결과에 원본 생년월일 미포함", "연·월·일 숫자열이 결과에 없음", "security")
def test_anonymize_birthdate_hides_raw():
    out = priv.anonymize_birthdate(date(1990, 4, 12), TODAY)
    assert "1990" not in out and "04" not in out and "12" not in out


@case("UT-PRIV-14", "FR-02", "process(pseudonym): 결과 객체", "level='pseudonym', pseudonym_id 형식 일치, 표시값 '홍*동 (30대)'")
def test_process_pseudonym():
    r = priv.process("pseudonym", "홍길동", date(1990, 4, 12), TODAY)
    assert r.level == "pseudonym" and re.fullmatch(r"PSN-[0-9a-f]{16}", r.pseudonym_id)
    assert r.masked_display_value == "홍*동 (30대)"


@case("UT-PRIV-15", "FR-02", "process(anonymous): 식별자 없음", "level='anonymous', pseudonym_id=None, 표시값 '익명'")
def test_process_anonymous():
    r = priv.process("anonymous", "홍길동", date(1990, 4, 12), TODAY)
    assert (r.level, r.pseudonym_id, r.masked_display_value) == ("anonymous", None, "익명")


@case("UT-PRIV-16", "FR-02", "process: 허용되지 않는 mode", "ValidationError", "negative")
@pytest.mark.parametrize("mode", ["", "PSEUDONYM", "none", None])
def test_process_invalid_mode(mode):
    with pytest.raises(ValidationError):
        priv.process(mode, "홍길동", date(1990, 4, 12), TODAY)


@case("UT-PRIV-17", "FR-02", "process(pseudonym): 잘못된 이름/미래 생년월일", "ValidationError", "negative")
def test_process_pseudonym_invalid_fields():
    with pytest.raises(ValidationError):
        priv.process("pseudonym", "", date(1990, 4, 12), TODAY)
    with pytest.raises(ValidationError):
        priv.process("pseudonym", "홍길동", date(2030, 1, 1), TODAY)


@case("UT-PRIV-18", "FR-02", "process: 어떤 결과 필드에도 원본 이름이 그대로 없음", "표시값/식별자에 '홍길동' 미포함", "security")
@pytest.mark.parametrize("mode", ["pseudonym", "anonymous"])
def test_process_result_has_no_raw_name(mode):
    r = priv.process(mode, "홍길동", date(1990, 4, 12), TODAY)
    assert "홍길동" not in f"{r.pseudonym_id}{r.masked_display_value}"


# ---------- 저장 (DB) ----------
@case("UT-PRIV-19", "FR-02", "process_and_store: personal_info 저장", "level·pseudonym_id·masked_display_value 가 처리 결과와 일치, user_id 당 1건")
def test_store_creates_row(session):
    u = factories.make_user(session)
    p = priv.process_and_store(session, u.id, "pseudonym", "홍길동", date(1990, 4, 12), TODAY)
    saved = session.get(PersonalInfo, p.id)
    assert saved.user_id == u.id and saved.anonymization_level == "pseudonym"
    assert saved.masked_display_value == "홍*동 (30대)" and saved.pseudonym_id.startswith("PSN-")


@case("UT-PRIV-20", "FR-02", "process_and_store: 재처리는 갱신(중복 행 없음), 기존 pseudonym_id 유지", "행 1건, pseudonym_id 동일")
def test_store_upsert_keeps_pseudonym(session):
    u = factories.make_user(session)
    p1 = priv.process_and_store(session, u.id, "pseudonym", "홍길동", date(1990, 4, 12), TODAY)
    first_id = p1.pseudonym_id
    priv.process_and_store(session, u.id, "pseudonym", "홍길순", date(1991, 1, 1), TODAY)
    assert session.scalar(select(func.count()).select_from(PersonalInfo)) == 1
    row = session.scalar(select(PersonalInfo))
    assert row.pseudonym_id == first_id and row.masked_display_value == "홍*순 (30대)"


@case("UT-PRIV-21", "FR-02", "process_and_store: 가명→익명 전환 시 pseudonym_id 제거", "level='anonymous', pseudonym_id=None")
def test_store_switch_to_anonymous(session):
    u = factories.make_user(session)
    priv.process_and_store(session, u.id, "pseudonym", "홍길동", date(1990, 4, 12), TODAY)
    priv.process_and_store(session, u.id, "anonymous", "홍길동", date(1990, 4, 12), TODAY)
    row = session.scalar(select(PersonalInfo))
    assert row.anonymization_level == "anonymous" and row.pseudonym_id is None and row.masked_display_value == "익명"


@case("UT-PRIV-22", "FR-02", "process_and_store: 없는 사용자", "NotFoundError, 행 미생성", "negative")
def test_store_unknown_user(session):
    with pytest.raises(NotFoundError):
        priv.process_and_store(session, 99999, "pseudonym", "홍길동", date(1990, 4, 12), TODAY)
    assert session.scalar(select(func.count()).select_from(PersonalInfo)) == 0


@case("UT-PRIV-23", "FR-02", "process_and_store: 원본 이름·생년월일이 DB 어느 테이블에도 저장되지 않음", "전 테이블 덤프에 '홍길동'/'1990-04-12' 없음", "security")
def test_store_never_persists_raw_pii(session):
    u = factories.make_user(session)
    priv.process_and_store(session, u.id, "pseudonym", "홍길동", date(1990, 4, 12), TODAY)
    dump = ""
    for (tbl,) in session.execute(text("SELECT name FROM sqlite_master WHERE type='table'")):
        dump += str(session.execute(text(f"SELECT * FROM {tbl}")).fetchall())
    assert "홍길동" not in dump and "1990-04-12" not in dump


@case("UT-PRIV-24", "FR-02", "get_privacy_info: 저장 후 조회 / 미처리 사용자", "저장된 행 반환, 없으면 NotFoundError")
def test_get_privacy_info(session):
    u = factories.make_user(session)
    with pytest.raises(NotFoundError):
        priv.get_privacy_info(session, u.id)
    priv.process_and_store(session, u.id, "anonymous", "홍길동", date(1990, 4, 12), TODAY)
    assert priv.get_privacy_info(session, u.id).anonymization_level == "anonymous"
