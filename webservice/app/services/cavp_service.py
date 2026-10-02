"""CAVP 시험 신청/조회 (FR-03). 계약만 정의.

- 허용 알고리즘: ALGORITHMS. 그 외/빈 값은 ValidationError.
- 동일 사용자·동일 알고리즘의 진행 중(submitted/reviewing) 신청이 있으면 DuplicateApplicationError.
  (approved/rejected 이후에는 재신청 허용)
- 상태 전이: submitted→reviewing→(approved|rejected). 그 외 InvalidTransitionError.
- 상태 변경은 institution 유형 사용자만 가능(PermissionDeniedError).
- 조회는 본인 신청만. 타인 신청 상세는 PermissionDeniedError (institution 은 전체 조회 가능).
- 목록: 최신순(submitted_at desc, id desc), page>=1, per_page 1~50, status 필터 선택.
"""
from ..models import CavpApplication

ALGORITHMS = ("AES", "SHA-2", "SHA-3", "HMAC", "RSA", "ECDSA", "DRBG")
STATUSES = ("submitted", "reviewing", "approved", "rejected")
TRANSITIONS = {
    "submitted": {"reviewing"},
    "reviewing": {"approved", "rejected"},
    "approved": set(),
    "rejected": set(),
}


def create_application(session, user_id: int, algorithm_type: str) -> CavpApplication:
    raise NotImplementedError


def update_status(session, actor_id: int, application_id: int, new_status: str) -> CavpApplication:
    raise NotImplementedError


def list_applications(session, user_id: int, status: str | None = None,
                      page: int = 1, per_page: int = 10) -> dict:
    """{'items': [CavpApplication], 'total': int, 'page': int, 'per_page': int}"""
    raise NotImplementedError


def get_application(session, user_id: int, application_id: int) -> CavpApplication:
    raise NotImplementedError
