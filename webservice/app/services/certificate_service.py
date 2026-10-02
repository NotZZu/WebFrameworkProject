"""검증서 이력 / 위변조 탐지 모의 (FR-04, FR-05). 계약만 정의.

- 검증서 원본 내용은 CERT_STORAGE_DIR/cert_<id>.bin 에 저장, 발급 시점의 SHA-256 을 integrity_hash 에 기록.
- verify_integrity: 파일을 다시 해시하여 비교. 불일치/파일 없음 → 'suspected', 일치 → 'normal' 로
  tamper_status 를 갱신·저장하고 Certificate 를 반환.
- 발급은 approved 상태의 신청에만 가능(InvalidTransitionError), 신청당 검증서 1건(DuplicateApplicationError).
- 발급은 institution 사용자만(PermissionDeniedError). 조회는 신청 소유자만.
"""
from ..models import Certificate


def compute_hash(content: bytes) -> str:
    """SHA-256 hex(64자)."""
    raise NotImplementedError


def compare_hash(expected: str, actual: str) -> str:
    """같으면 'normal', 다르면 'suspected'. 대소문자 차이는 같은 값으로 취급."""
    raise NotImplementedError


def issue_certificate(session, actor_id: int, application_id: int, cert_type: str,
                      content: bytes, storage_dir: str) -> Certificate:
    raise NotImplementedError


def list_certificates(session, user_id: int, page: int = 1, per_page: int = 10) -> dict:
    """본인 신청에 속한 검증서만. issued_at 내림차순. 형식은 cavp 목록과 동일."""
    raise NotImplementedError


def get_certificate(session, user_id: int, certificate_id: int) -> Certificate:
    raise NotImplementedError


def verify_integrity(session, certificate_id: int, storage_dir: str) -> Certificate:
    raise NotImplementedError
