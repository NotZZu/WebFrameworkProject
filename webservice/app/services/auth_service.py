"""인증 서비스 (FR-01).

정책(시험계획서 v1.1 가정 A-01~A-04)
- username: 4~20자, 영문/숫자/밑줄만. 대소문자 구분.
- password: 8~64자, 영문과 숫자를 각 1자 이상 포함. bcrypt 해시로만 저장.
- user_type: individual | company | institution. company/institution 은 org_code 필수.
- 로그인 실패 시 '아이디 없음'과 '비밀번호 불일치'를 구분하지 않는다.
"""
import re

import bcrypt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..errors import AuthenticationError, DuplicateUsernameError, NotFoundError, ValidationError
from ..models import User

USER_TYPES = ("individual", "company", "institution")
_USERNAME_RE = re.compile(r"[A-Za-z0-9_]{4,20}")
_BCRYPT_MAX = 72  # bcrypt 는 72바이트 초과 입력을 처리하지 못하므로 잘라서 사용
LOGIN_FAILED_MESSAGE = "아이디 또는 비밀번호가 올바르지 않습니다."
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password-0", bcrypt.gensalt(rounds=4)).decode()


def _pw_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_pw_bytes(plain), bcrypt.gensalt()).decode()


def verify_password(plain, hashed) -> bool:
    if not isinstance(plain, str) or not plain or not isinstance(hashed, str) or not hashed:
        return False
    try:
        return bcrypt.checkpw(_pw_bytes(plain), hashed.encode())
    except (ValueError, TypeError):
        return False


def _validate_username(username) -> str:
    if not isinstance(username, str) or not _USERNAME_RE.fullmatch(username):
        raise ValidationError("아이디는 4~20자의 영문, 숫자, 밑줄(_)만 사용할 수 있습니다.")
    return username


def _validate_password(password) -> str:
    if (not isinstance(password, str) or not 8 <= len(password) <= 64
            or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password)):
        raise ValidationError("비밀번호는 8~64자이며 영문과 숫자를 각각 1자 이상 포함해야 합니다.")
    return password


def signup(session, username, password, user_type, org_code=None) -> User:
    _validate_username(username)
    _validate_password(password)
    if user_type not in USER_TYPES:
        raise ValidationError("사용자 유형은 개인/기업/기관 중 하나여야 합니다.")
    if user_type == "individual":
        org_code = None
    else:
        org_code = org_code.strip() if isinstance(org_code, str) else ""
        if not org_code:
            raise ValidationError("기업/기관 사용자는 기관 코드가 필요합니다.")
    if session.scalar(select(User).where(User.username == username)):
        raise DuplicateUsernameError("이미 사용 중인 아이디입니다.")
    user = User(username=username, password_hash=hash_password(password),
                user_type=user_type, org_code=org_code)
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise DuplicateUsernameError("이미 사용 중인 아이디입니다.")
    return user


def login(session, username, password) -> User:
    user = None
    if isinstance(username, str) and username:
        user = session.scalar(select(User).where(User.username == username))
    # 계정 존재 여부와 무관하게 해시 비교를 수행(응답 시간 차이 최소화)
    ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        raise AuthenticationError(LOGIN_FAILED_MESSAGE)
    return user


def get_user(session, user_id) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    return user
