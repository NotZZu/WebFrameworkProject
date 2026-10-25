"""CAVP 시험 신청/조회 (FR-03). 계약만 정의.

- 허용 알고리즘: ALGORITHMS. 그 외/빈 값은 ValidationError.
- 동일 사용자·동일 알고리즘의 진행 중(submitted/reviewing) 신청이 있으면 DuplicateApplicationError.
  (approved/rejected 이후에는 재신청 허용)
- 상태 전이: submitted→reviewing→(approved|rejected). 그 외 InvalidTransitionError.
- 상태 변경은 institution 유형 사용자만 가능(PermissionDeniedError).
- 조회는 본인 신청만. 타인 신청 상세는 PermissionDeniedError (institution 은 전체 조회 가능).
- 목록: 최신순(submitted_at desc, id desc), page>=1, per_page 1~50, status 필터 선택.
"""
from sqlalchemy import func, select

from ..errors import DuplicateApplicationError, NotFoundError, ValidationError
from ..models import CavpApplication, User
from .dashboard_service import STATUS_LABELS

ALGORITHMS = ("AES", "SHA-2", "SHA-3", "HMAC", "RSA", "ECDSA", "DRBG")
STATUSES = ("submitted", "reviewing", "approved", "rejected")
TRANSITIONS = {
    "submitted": {"reviewing"},
    "reviewing": {"approved", "rejected"},
    "approved": set(),
    "rejected": set(),
}


def create_application(session, user_id: int, algorithm_type: str) -> CavpApplication:
    if not isinstance(algorithm_type, str) or algorithm_type not in ALGORITHMS:
        raise ValidationError("시험 대상 알고리즘을 목록에서 선택해 주세요.")
    if session.get(User, user_id) is None:
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    active = session.scalar(
        select(func.count()).select_from(CavpApplication).where(
            CavpApplication.user_id == user_id,
            CavpApplication.algorithm_type == algorithm_type,
            CavpApplication.status.in_(("submitted", "reviewing"))))
    if active:
        raise DuplicateApplicationError("같은 알고리즘의 진행 중인 신청이 있습니다.")
    app = CavpApplication(user_id=user_id, algorithm_type=algorithm_type, status="submitted")
    session.add(app)
    session.commit()
    return app


def _int_in_range(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValidationError(f"{name} 값이 올바르지 않습니다.")
    return value


def update_status(session, actor_id: int, application_id: int, new_status: str) -> CavpApplication:
    raise NotImplementedError


def list_applications(session, user_id: int, status: str | None = None,
                      page: int = 1, per_page: int = 10) -> dict:
    """{'items': [CavpApplication], 'total': int, 'page': int, 'per_page': int}"""
    _int_in_range(page, "page", 1, 1_000_000)
    _int_in_range(per_page, "per_page", 1, 50)
    if status is not None and status not in STATUSES:
        raise ValidationError("상태 값이 올바르지 않습니다.")
    cond = [CavpApplication.user_id == user_id]
    if status is not None:
        cond.append(CavpApplication.status == status)
    total = session.scalar(select(func.count()).select_from(CavpApplication).where(*cond))
    items = session.scalars(
        select(CavpApplication).where(*cond)
        .order_by(CavpApplication.submitted_at.desc(), CavpApplication.id.desc())
        .limit(per_page).offset((page - 1) * per_page)).all()
    return {"items": items, "total": total, "page": page, "per_page": per_page}


def get_application(session, user_id: int, application_id: int) -> CavpApplication:
    raise NotImplementedError
