"""가명·익명정보 처리 모의 (FR-02). 계약만 정의.

- mode='pseudonym': pseudonym_id 발급 + 이름 마스킹 + 생년월일 연령대 치환.
- mode='anonymous': pseudonym_id 없음, 표시값은 '익명'. 개인 식별 가능 값은 어디에도 남기지 않는다.
- 원본(이름/생년월일/전화/이메일)은 DB 어느 테이블에도 저장하지 않는다.
"""
from dataclasses import dataclass
from datetime import date

from ..models import PersonalInfo


@dataclass(frozen=True)
class PrivacyResult:
    level: str                    # 'pseudonym' | 'anonymous'
    pseudonym_id: str | None      # anonymous 이면 None
    masked_display_value: str     # 화면 표시값 (예: '홍*동 (30대)')


def issue_pseudonym_id() -> str:
    """'PSN-' + 16자리 소문자 hex. 호출마다 다른 값."""
    raise NotImplementedError


def mask_name(name: str) -> str:
    """'홍길동'→'홍*동', '홍길'→'홍*', '홍'→'*', 'John'→'J**n'. 공백/빈 문자열은 ValidationError."""
    raise NotImplementedError


def mask_phone(phone: str) -> str:
    """'010-1234-5678' / '01012345678' → '010-****-5678'. 형식 오류는 ValidationError."""
    raise NotImplementedError


def anonymize_birthdate(birth: date, today: date | None = None) -> str:
    """만 나이 기준 연령대 문자열('30대'). 10세 미만 '10세 미만', 100세 이상 '100세 이상'. 미래 날짜는 ValidationError."""
    raise NotImplementedError


def process(mode: str, name: str, birthdate: date, today: date | None = None) -> PrivacyResult:
    """DB 접근 없는 순수 변환. mode 오류는 ValidationError."""
    raise NotImplementedError


def process_and_store(session, user_id: int, mode: str, name: str, birthdate: date,
                      today: date | None = None) -> PersonalInfo:
    """process 결과를 personal_info 에 저장(user_id 당 1건, 재호출 시 갱신). 없는 사용자 NotFoundError."""
    raise NotImplementedError


def get_privacy_info(session, user_id: int) -> PersonalInfo:
    """없으면 NotFoundError."""
    raise NotImplementedError
