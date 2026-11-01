"""초기 데이터 적재 (시스템설계서 v1.1 5.3절 / D12).

seed(session, storage_dir=None) → {'users': n, 'personal_info': n, 'applications': n, 'certificates': n}
- 사용자 3종(demo_individual, demo_company, demo_institution), 공통 비밀번호 'Demo1234'(bcrypt 저장).
- 신청 6건(4개 상태 모두 포함), 검증서 3건(그중 1건은 원본과 내용이 달라 tamper_status='suspected').
- 개인정보는 가명/익명 처리값만 저장한다(원본 이름·생년월일은 저장하지 않음).
- 멱등: 두 번 실행해도 건수가 늘지 않는다. 서비스 계층만 거치므로 SQL·DynamoDB 어느 저장소에서도 같게 동작한다.
- 실행: python -m app.seed  (STORE_BACKEND/DYNAMODB_TABLE 등 환경변수를 따른다)
"""
import os
import tempfile
from datetime import date

from .services import auth_service, cavp_service, certificate_service, privacy_service
from .store import as_store

DEMO_PASSWORD = "Demo1234"
_USERS = (
    ("demo_individual", "individual", None),
    ("demo_company", "company", "DEMO-COMPANY"),
    ("demo_institution", "institution", "DEMO-INSTITUTE"),
)
# (소유자, 알고리즘, 최종 상태, 검증서 유형, 검증서 내용, 위변조 여부)
_APPS = (
    ("demo_individual", "AES", "approved", "CAVP", "AES 알고리즘 검증 결과: 모든 시험 벡터 통과", False),
    ("demo_individual", "RSA", "submitted", None, None, False),
    ("demo_individual", "DRBG", "rejected", None, None, False),
    ("demo_company", "HMAC", "approved", "CAVP", "HMAC 알고리즘 검증 결과: 모든 시험 벡터 통과", False),
    ("demo_company", "ECDSA", "reviewing", None, None, False),
    ("demo_company", "SHA-3", "approved", "KCMVP", "SHA-3 알고리즘 검증 결과: 모든 시험 벡터 통과", True),
)
_PRIVACY = (("demo_individual", "pseudonym", "홍길동", date(1995, 3, 14)),
            ("demo_company", "anonymous", "김철수", date(1988, 7, 2)))


def _storage_dir(storage_dir):
    return storage_dir or os.environ.get("CERT_STORAGE_DIR") or os.path.join(tempfile.gettempdir(), "seed_certs")


def seed(session, storage_dir=None) -> dict:
    store = as_store(session)
    users = {}
    for username, user_type, org in _USERS:
        user = store.get_user_by_username(username)
        users[username] = user or auth_service.signup(session, username, DEMO_PASSWORD, user_type, org)
    officer = users["demo_institution"]

    for username, mode, name, birth in _PRIVACY:
        if store.get_personal_info(users[username].id) is None:
            privacy_service.process_and_store(session, users[username].id, mode, name, birth)

    if all(store.list_applications(u.id, None, 1, 1)[1] == 0 for u in users.values()):
        directory = _storage_dir(storage_dir)
        for owner, algo, final, cert_type, content, tampered in _APPS:
            app = cavp_service.create_application(session, users[owner].id, algo)
            if final in ("reviewing", "approved", "rejected"):
                cavp_service.update_status(session, officer.id, app.id, "reviewing")
            if final in ("approved", "rejected"):
                cavp_service.update_status(session, officer.id, app.id, final)
            if cert_type and not tampered:
                certificate_service.issue_certificate(
                    session, officer.id, app.id, cert_type, content.encode("utf-8"), directory)
            elif cert_type:  # 발급 뒤 내용이 바뀐 검증서: 기록된 해시는 원본 것, 저장된 내용은 위조본
                cert = store.create_certificate(app.id, cert_type, certificate_service.compute_hash(content.encode("utf-8")),
                                                b"forged content", directory)
                store.set_tamper_status(cert.id, "suspected")

    apps = store.list_applications(None, None, 1, 1)[1]
    certs = len(store.list_certificates(None))
    info = sum(store.get_personal_info(u.id) is not None for u in users.values())
    return {"users": len(users), "personal_info": info, "applications": apps, "certificates": certs}


if __name__ == "__main__":  # pragma: no cover
    from . import create_app
    _app = create_app()
    _store = _app.store_factory()
    try:
        print(seed(_store, _app.config.get("CERT_STORAGE_DIR")))
    finally:
        _store.close()
