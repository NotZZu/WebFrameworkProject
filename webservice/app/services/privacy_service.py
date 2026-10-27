"""가명·익명정보 처리 (FR-02, SC-03).

- mode='pseudonym': pseudonym_id 발급 + 이름 마스킹 + 생년월일 연령대 치환.
- mode='anonymous': pseudonym_id 없음, 표시값은 '익명'. 개인 식별 가능 값은 어디에도 남기지 않는다.
- 원본(이름/생년월일/전화/이메일)은 DB 어느 테이블에도 저장하지 않는다.

구현 메모(공격 대비):
- 이름은 공백을 뺀 뒤 1~50자, 제어문자·줄바꿈 불가(로그·CSV 주입 방지). 문자열이 아니면 ValidationError.
- 오류 메시지에는 입력값(이름·생년월일)을 절대 싣지 않는다.
- 가명 ID 는 secrets 로 만든 예측 불가 난수. 같은 사용자가 다시 처리해도 기존 가명 ID 를 유지한다(저장소가 보장).
"""
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import date

from ..errors import NotFoundError, ValidationError
from ..models import PersonalInfo
from ..store import as_store

MODES = ("pseudonym", "anonymous")
MAX_NAME_LEN = 50


@dataclass(frozen=True)
class PrivacyResult:
    level: str                    # 'pseudonym' | 'anonymous'
    pseudonym_id: str | None      # anonymous 이면 None
    masked_display_value: str     # 화면 표시값 (예: '홍*동 (30대)')


def issue_pseudonym_id() -> str:
    """'PSN-' + 16자리 소문자 hex. 호출마다 다른 값."""
    return "PSN-" + secrets.token_hex(8)


def mask_name(name: str) -> str:
    """'홍길동'→'홍*동', '홍길'→'홍*', '홍'→'*', 'John'→'J**n'. 공백/빈 문자열은 ValidationError."""
    if not isinstance(name, str):
        raise ValidationError("이름을 입력해 주세요.")
    name = name.strip()
    if not name:
        raise ValidationError("이름을 입력해 주세요.")
    if len(name) > MAX_NAME_LEN:
        raise ValidationError(f"이름은 {MAX_NAME_LEN}자 이하여야 합니다.")
    if any(unicodedata.category(ch).startswith("C") for ch in name):
        raise ValidationError("이름에 사용할 수 없는 문자가 있습니다.")
    if len(name) == 1:
        return "*"
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


_PHONE = re.compile(r"^(01[016789])-?(\d{3,4})-?(\d{4})$")


def mask_phone(phone: str) -> str:
    """'010-1234-5678' / '01012345678' → '010-****-5678'. 형식 오류는 ValidationError."""
    m = _PHONE.fullmatch(phone.strip()) if isinstance(phone, str) else None
    if not m:
        raise ValidationError("전화번호 형식이 올바르지 않습니다.")
    return f"{m.group(1)}-{'*' * len(m.group(2))}-{m.group(3)}"


def anonymize_birthdate(birth: date, today: date | None = None) -> str:
    """만 나이 기준 연령대 문자열('30대'). 10세 미만 '10세 미만', 100세 이상 '100세 이상'. 미래 날짜는 ValidationError."""
    if not isinstance(birth, date):
        raise ValidationError("생년월일이 올바르지 않습니다.")
    today = today or date.today()
    if birth > today:
        raise ValidationError("생년월일이 올바르지 않습니다.")
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    if age < 10:
        return "10세 미만"
    if age >= 100:
        return "100세 이상"
    return f"{age // 10 * 10}대"


def process(mode: str, name: str, birthdate: date, today: date | None = None) -> PrivacyResult:
    """DB 접근 없는 순수 변환. mode 오류는 ValidationError."""
    if mode not in MODES:
        raise ValidationError("처리 방식은 pseudonym 또는 anonymous 여야 합니다.")
    masked, age_band = mask_name(name), anonymize_birthdate(birthdate, today)  # 익명이어도 입력은 검증한다
    if mode == "anonymous":
        return PrivacyResult("anonymous", None, "익명")
    return PrivacyResult("pseudonym", issue_pseudonym_id(), f"{masked} ({age_band})")


def process_and_store(session, user_id: int, mode: str, name: str, birthdate: date,
                      today: date | None = None) -> PersonalInfo:
    """process 결과를 personal_info 에 저장(user_id 당 1건, 재호출 시 갱신). 없는 사용자 NotFoundError.
    원본 이름·생년월일은 이 함수 안에서만 쓰이고 어디에도 저장되지 않는다."""
    store = as_store(session)
    result = process(mode, name, birthdate, today)
    if store.get_user(user_id) is None:
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    return store.upsert_personal_info(user_id, result.level, result.pseudonym_id, result.masked_display_value)


def get_privacy_info(session, user_id: int) -> PersonalInfo:
    """없으면 NotFoundError."""
    info = as_store(session).get_personal_info(user_id)
    if info is None:
        raise NotFoundError("처리된 개인정보가 없습니다.")
    return info
