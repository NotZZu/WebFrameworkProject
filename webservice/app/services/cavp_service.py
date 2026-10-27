"""CAVP 시험 신청/조회 (FR-03). 계약만 정의.

- 허용 알고리즘: ALGORITHMS. 그 외/빈 값은 ValidationError.
- 동일 사용자·동일 알고리즘의 진행 중(submitted/reviewing) 신청이 있으면 DuplicateApplicationError.
  (approved/rejected 이후에는 재신청 허용)
- 상태 전이: submitted→reviewing→(approved|rejected). 그 외 InvalidTransitionError.
- 상태 변경은 institution 유형 사용자만 가능(PermissionDeniedError).
- 조회는 본인 신청만. 타인 신청 상세는 PermissionDeniedError (institution 은 전체 조회 가능).
- 목록: 최신순(submitted_at desc, id desc), page>=1, per_page 1~50, status 필터 선택.
"""
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from ..errors import (DuplicateApplicationError, InvalidTransitionError, NotFoundError,
                      PermissionDeniedError, ValidationError)
from ..store import as_store
from .dashboard_service import STATUS_LABELS

ALGORITHMS = ("AES", "SHA-2", "SHA-3", "HMAC", "RSA", "ECDSA", "DRBG")
STATUSES = ("submitted", "reviewing", "approved", "rejected")
TRANSITIONS = {
    "submitted": {"reviewing"},
    "reviewing": {"approved", "rejected"},
    "approved": set(),
    "rejected": set(),
}


def create_application(session, user_id: int, algorithm_type: str):
    store = as_store(session)
    if not isinstance(algorithm_type, str) or algorithm_type not in ALGORITHMS:
        raise ValidationError("시험 대상 알고리즘을 목록에서 선택해 주세요.")
    if store.get_user(user_id) is None:
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    return store.create_application(user_id, algorithm_type)


def _int_in_range(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValidationError(f"{name} 값이 올바르지 않습니다.")
    return value


def update_status(session, actor_id: int, application_id: int, new_status: str):
    store = as_store(session)
    actor = store.get_user(actor_id)
    if actor is None:
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    if actor.user_type != "institution":
        raise PermissionDeniedError("신청 상태는 기관 사용자만 변경할 수 있습니다.")
    app = store.get_application(application_id)
    if app is None:
        raise NotFoundError("신청을 찾을 수 없습니다.")
    if not isinstance(new_status, str) or new_status not in STATUSES:
        raise ValidationError("상태 값이 올바르지 않습니다.")
    if new_status not in TRANSITIONS[app.status]:
        raise InvalidTransitionError(f"'{STATUS_LABELS[app.status]}' 상태에서는 '{STATUS_LABELS[new_status]}'(으)로 변경할 수 없습니다.")
    # 읽은 뒤 다른 요청이 먼저 바꿨을 수 있으므로, '내가 읽은 상태일 때만' 바꾸는 한 번의 동작으로 처리한다(DF-14).
    if not store.change_application_status(application_id, app.status, new_status):
        raise InvalidTransitionError("다른 요청이 먼저 상태를 변경했습니다. 목록을 새로 고친 뒤 다시 시도해 주세요.")
    return store.get_application(application_id)


def list_applications(session, user_id: int, status: str | None = None,
                      page: int = 1, per_page: int = 10, include_all: bool = False) -> dict:
    """{'items': [CavpApplication], 'total': int, 'page': int, 'per_page': int}"""
    _int_in_range(page, "page", 1, 1_000_000)
    _int_in_range(per_page, "per_page", 1, 50)
    if status is not None and status not in STATUSES:
        raise ValidationError("상태 값이 올바르지 않습니다.")
    items, total = as_store(session).list_applications(None if include_all else user_id, status, page, per_page)
    return {"items": items, "total": total, "page": page, "per_page": per_page}


def get_application(session, user_id: int, application_id: int):
    store = as_store(session)
    user = store.get_user(user_id)
    if user is None:
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    app = store.get_application(application_id)
    if app is None:
        raise NotFoundError("신청을 찾을 수 없습니다.")
    if app.user_id != user_id and user.user_type != "institution":
        raise PermissionDeniedError("다른 사용자의 신청은 조회할 수 없습니다.")
    return app
