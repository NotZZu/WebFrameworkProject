"""검증서 이력 조회 / 위변조 탐지 (FR-04, FR-05, SC-06·SC-07).

- 검증서 원본 내용은 저장소(SQL=CERT_STORAGE_DIR/cert_<id>.bin 파일, DynamoDB=표의 항목)에 두고,
  발급 시점의 SHA-256 을 integrity_hash 에 기록한다.
- verify_integrity: 내용을 다시 해시하여 비교. 불일치/내용 없음 → 'suspected', 일치 → 'normal' 로
  tamper_status 를 갱신·저장하고 Certificate 를 반환한다(integrity_hash 는 바꾸지 않는다).
- 발급은 approved 상태의 신청에만 가능(InvalidTransitionError), 신청당 검증서 1건(DuplicateApplicationError).
- 발급은 institution 사용자만(PermissionDeniedError). 조회·검증은 신청 소유자 또는 기관 사용자만
  (기관은 신청과 같이 전체를 본다).
- 내용은 1바이트 이상 MAX_CONTENT_BYTES 이하. 오류 메시지에 내용·해시·저장 경로를 싣지 않는다.
"""
import hashlib
import hmac

from ..errors import (DuplicateApplicationError, InvalidTransitionError, NotFoundError,
                      PermissionDeniedError, ValidationError)
from ..models import Certificate
from ..store import as_store

CERT_TYPES = ("CAVP", "KCMVP")
MAX_CONTENT_BYTES = 60_000


def compute_hash(content: bytes) -> str:
    """SHA-256 hex(64자)."""
    return hashlib.sha256(content).hexdigest()


def compare_hash(expected: str, actual: str) -> str:
    """같으면 'normal', 다르면 'suspected'. 대소문자 차이는 같은 값으로 취급."""
    same = hmac.compare_digest(str(expected).lower().encode(), str(actual).lower().encode())  # 시간차 비교 방지
    return "normal" if same else "suspected"


def issue_certificate(session, actor_id: int, application_id: int, cert_type: str,
                      content: bytes, storage_dir: str) -> Certificate:
    store = as_store(session)
    actor = store.get_user(actor_id)
    if actor is None:
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    if actor.user_type != "institution":
        raise PermissionDeniedError("검증서는 기관 사용자만 발급할 수 있습니다.")
    if not isinstance(cert_type, str) or cert_type not in CERT_TYPES:
        raise ValidationError("검증서 유형이 올바르지 않습니다.")
    if not isinstance(content, (bytes, bytearray)) or not content:
        raise ValidationError("검증서 내용을 입력해 주세요.")
    if len(content) > MAX_CONTENT_BYTES:
        raise ValidationError("검증서 내용이 너무 깁니다.")
    app = store.get_application(application_id)
    if app is None:
        raise NotFoundError("신청을 찾을 수 없습니다.")
    if app.status != "approved":
        raise InvalidTransitionError("승인된 신청에만 검증서를 발급할 수 있습니다.")
    return store.create_certificate(application_id, cert_type, compute_hash(bytes(content)), bytes(content), storage_dir)


def _int_in_range(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValidationError(f"{name} 값이 올바르지 않습니다.")
    return value


def list_certificates(session, user_id: int, page: int = 1, per_page: int = 10, include_all: bool = False) -> dict:
    """본인 신청에 속한 검증서만(include_all 이면 전체). issued_at 내림차순. 형식은 cavp 목록과 동일."""
    _int_in_range(page, "page", 1, 1_000_000)
    _int_in_range(per_page, "per_page", 1, 50)
    items = as_store(session).list_certificates(None if include_all else user_id)
    items = sorted(items, key=lambda c: (c.issued_at, c.id), reverse=True)
    start = (page - 1) * per_page
    return {"items": items[start:start + per_page], "total": len(items), "page": page, "per_page": per_page}


def get_certificate(session, user_id: int, certificate_id: int) -> Certificate:
    store = as_store(session)
    user = store.get_user(user_id)
    if user is None:
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    cert = store.get_certificate(certificate_id)
    if cert is None:
        raise NotFoundError("검증서를 찾을 수 없습니다.")
    app = store.get_application(cert.application_id)
    if (app is None or app.user_id != user_id) and user.user_type != "institution":
        raise PermissionDeniedError("다른 사용자의 검증서는 조회할 수 없습니다.")
    return cert


def verify_integrity(session, certificate_id: int, storage_dir: str) -> Certificate:
    store = as_store(session)
    cert = store.get_certificate(certificate_id)
    if cert is None:
        raise NotFoundError("검증서를 찾을 수 없습니다.")
    content = store.read_certificate_content(certificate_id, storage_dir)
    status = "suspected" if content is None else compare_hash(cert.integrity_hash, compute_hash(content))
    return store.set_tamper_status(certificate_id, status)
