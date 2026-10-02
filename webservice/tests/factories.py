"""테스트 데이터 직접 삽입 헬퍼 (서비스 코드를 거치지 않으므로 Red 단계에서도 동작)."""
import bcrypt

from app.models import Certificate, CavpApplication, PersonalInfo, User

DEFAULT_PASSWORD = "Passw0rd1"
_HASH = bcrypt.hashpw(DEFAULT_PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()
_seq = {"n": 0}


def _next() -> int:
    _seq["n"] += 1
    return _seq["n"]


def make_user(session, username=None, user_type="individual", org_code=None) -> User:
    username = username or f"user_{_next()}"
    if user_type in ("company", "institution") and org_code is None:
        org_code = "ORG-001"
    u = User(username=username, password_hash=_HASH, user_type=user_type, org_code=org_code)
    session.add(u)
    session.commit()
    return u


def make_application(session, user, algorithm_type="AES", status="submitted") -> CavpApplication:
    a = CavpApplication(user_id=user.id, algorithm_type=algorithm_type, status=status)
    session.add(a)
    session.commit()
    return a


def make_certificate(session, application, cert_type="CAVP", integrity_hash="a" * 64,
                     tamper_status="normal") -> Certificate:
    c = Certificate(application_id=application.id, cert_type=cert_type,
                    integrity_hash=integrity_hash, tamper_status=tamper_status)
    session.add(c)
    session.commit()
    return c


def make_personal_info(session, user, level="pseudonym") -> PersonalInfo:
    p = PersonalInfo(user_id=user.id, anonymization_level=level,
                     pseudonym_id="PSN-0123456789abcdef" if level == "pseudonym" else None,
                     masked_display_value="홍*동 (30대)" if level == "pseudonym" else "익명")
    session.add(p)
    session.commit()
    return p
