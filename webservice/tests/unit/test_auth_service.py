"""단위시험 UT-AUTH — FR-01 회원가입/로그인 (AuthService)."""
import pytest
from sqlalchemy import func, select

from app.errors import AuthenticationError, DuplicateUsernameError, NotFoundError, ValidationError
from app.models import User
from app.services import auth_service as auth
from tests import factories
from tests.case_registry import case

PW = "Passw0rd1"


def count_users(session):
    return session.scalar(select(func.count()).select_from(User))


# ---------- hash / verify ----------
@case("UT-AUTH-01", "FR-01", "hash_password: 원문과 다른 bcrypt 해시", "원문과 다르며 '$2' 로 시작하는 bcrypt 해시 문자열")
def test_hash_password_returns_bcrypt_hash():
    h = auth.hash_password(PW)
    assert h != PW and h.startswith("$2") and len(h) >= 59


@case("UT-AUTH-02", "FR-01", "hash_password: 동일 입력도 salt 로 매번 다른 해시", "두 번 호출한 해시가 서로 다름")
def test_hash_password_is_salted():
    assert auth.hash_password(PW) != auth.hash_password(PW)


@case("UT-AUTH-03", "FR-01", "verify_password: 올바른 평문", "True")
def test_verify_password_ok():
    assert auth.verify_password(PW, auth.hash_password(PW)) is True


@case("UT-AUTH-04", "FR-01", "verify_password: 잘못된 평문", "False", "negative")
def test_verify_password_wrong():
    assert auth.verify_password("Wrong0000", auth.hash_password(PW)) is False


@case("UT-AUTH-05", "FR-01", "verify_password: 대소문자 구분", "대소문자만 다른 평문은 False", "boundary")
def test_verify_password_case_sensitive():
    assert auth.verify_password(PW.lower(), auth.hash_password(PW)) is False


@case("UT-AUTH-06", "FR-01", "verify_password: 빈 입력/깨진 해시는 예외 없이 False", "예외 없이 False", "negative")
@pytest.mark.parametrize("plain,hashed", [("", "$2b$04$" + "a" * 53), (PW, ""), (PW, "not-a-hash"), (PW, None)])
def test_verify_password_bad_inputs_return_false(plain, hashed):
    assert auth.verify_password(plain, hashed) is False


@case("UT-AUTH-07", "FR-01", "hash_password: 한글·특수문자 포함 비밀번호", "해시 생성 후 verify 가 True", "boundary")
def test_hash_password_unicode():
    pw = "비밀번호Pass1!@#"
    assert auth.verify_password(pw, auth.hash_password(pw)) is True


# ---------- signup ----------
@case("UT-AUTH-08", "FR-01", "signup: 개인 사용자 가입", "User 생성, password_hash 는 원문과 다른 bcrypt 값, org_code 는 None")
def test_signup_individual(session):
    u = auth.signup(session, "alice01", PW, "individual")
    saved = session.get(User, u.id)
    assert saved.username == "alice01" and saved.user_type == "individual" and saved.org_code is None
    assert saved.password_hash != PW and saved.password_hash.startswith("$2")


@case("UT-AUTH-09", "FR-01", "signup: 기업/기관 사용자는 org_code 와 함께 가입", "user_type·org_code 가 그대로 저장")
@pytest.mark.parametrize("utype", ["company", "institution"])
def test_signup_org_types(session, utype):
    u = auth.signup(session, f"{utype}_01", PW, utype, org_code="ORG-777")
    assert u.user_type == utype and u.org_code == "ORG-777"


@case("UT-AUTH-10", "FR-01", "signup: 기업/기관인데 org_code 누락", "ValidationError, 사용자 미생성", "negative")
@pytest.mark.parametrize("utype", ["company", "institution"])
@pytest.mark.parametrize("org", [None, "", "   "])
def test_signup_org_requires_org_code(session, utype, org):
    with pytest.raises(ValidationError):
        auth.signup(session, "orguser01", PW, utype, org_code=org)
    assert count_users(session) == 0


@case("UT-AUTH-11", "FR-01", "signup: 개인 사용자가 org_code 를 보내도 저장하지 않음", "org_code 는 None", "boundary")
def test_signup_individual_ignores_org_code(session):
    assert auth.signup(session, "alice01", PW, "individual", org_code="ORG-1").org_code is None


@case("UT-AUTH-12", "FR-01", "signup: 중복 username", "DuplicateUsernameError, users 레코드 1건 유지", "negative")
def test_signup_duplicate_username(session):
    auth.signup(session, "alice01", PW, "individual")
    with pytest.raises(DuplicateUsernameError):
        auth.signup(session, "alice01", PW, "company", org_code="X")
    assert count_users(session) == 1


@case("UT-AUTH-13", "FR-01", "signup: username 은 대소문자를 구분(Alice01 ≠ alice01)", "두 계정 모두 생성", "boundary")
def test_signup_username_case_sensitive(session):
    auth.signup(session, "Alice01", PW, "individual")
    auth.signup(session, "alice01", PW, "individual")
    assert count_users(session) == 2


@case("UT-AUTH-14", "FR-01", "signup: username 길이 경계 3/4/20/21자", "4~20자만 허용, 나머지 ValidationError", "boundary")
@pytest.mark.parametrize("name,ok", [("abc", False), ("abcd", True), ("a" * 20, True), ("a" * 21, False)])
def test_signup_username_length(session, name, ok):
    if ok:
        assert auth.signup(session, name, PW, "individual").username == name
    else:
        with pytest.raises(ValidationError):
            auth.signup(session, name, PW, "individual")
        assert count_users(session) == 0


@case("UT-AUTH-15", "FR-01", "signup: username 허용 문자(영문/숫자/_) 외 입력", "ValidationError", "negative")
@pytest.mark.parametrize("name", ["", "    ", "al ice01", "alice-01", "alice@01", "홍길동홍길동", "alice01\n", "' OR '1'='1", "<script>x</script>"])
def test_signup_username_invalid_chars(session, name):
    with pytest.raises(ValidationError):
        auth.signup(session, name, PW, "individual")
    assert count_users(session) == 0


@case("UT-AUTH-16", "FR-01", "signup: 비밀번호 길이 경계 7/8/64/65자", "8~64자만 허용", "boundary")
@pytest.mark.parametrize("pw,ok", [("Pass123", False), ("Pass1234", True), ("P1" + "a" * 62, True), ("P1" + "a" * 63, False)])
def test_signup_password_length(session, pw, ok):
    if ok:
        auth.signup(session, "alice01", pw, "individual")
    else:
        with pytest.raises(ValidationError):
            auth.signup(session, "alice01", pw, "individual")
        assert count_users(session) == 0


@case("UT-AUTH-17", "FR-01", "signup: 비밀번호 구성 규칙(영문+숫자 각 1자 이상)", "숫자만/영문만/공백만 → ValidationError", "negative")
@pytest.mark.parametrize("pw", ["12345678", "abcdefgh", "        ", "", None])
def test_signup_password_composition(session, pw):
    with pytest.raises(ValidationError):
        auth.signup(session, "alice01", pw, "individual")


@case("UT-AUTH-18", "FR-01", "signup: 허용되지 않는 user_type", "ValidationError", "negative")
@pytest.mark.parametrize("utype", ["", "admin", "INDIVIDUAL", None])
def test_signup_invalid_user_type(session, utype):
    with pytest.raises(ValidationError):
        auth.signup(session, "alice01", PW, utype)


@case("UT-AUTH-19", "FR-01", "signup: 실패한 가입은 레코드를 남기지 않음(원자성)", "예외 후 users 0건", "negative")
def test_signup_failure_leaves_no_row(session):
    with pytest.raises(ValidationError):
        auth.signup(session, "ab", PW, "individual")
    assert count_users(session) == 0


# ---------- login / get_user ----------
@case("UT-AUTH-20", "FR-01", "login: 올바른 자격 증명", "해당 User 반환")
def test_login_ok(session):
    u = factories.make_user(session, "alice01")
    assert auth.login(session, "alice01", factories.DEFAULT_PASSWORD).id == u.id


@case("UT-AUTH-21", "FR-01", "login: 비밀번호 불일치", "AuthenticationError", "negative")
def test_login_wrong_password(session):
    factories.make_user(session, "alice01")
    with pytest.raises(AuthenticationError):
        auth.login(session, "alice01", "Wrong0000")


@case("UT-AUTH-22", "FR-01", "login: 없는 아이디 — 비밀번호 불일치와 동일한 예외/메시지", "AuthenticationError, 메시지가 UT-AUTH-21 과 동일(계정 존재 여부 비노출)", "security")
def test_login_unknown_user_same_error(session):
    factories.make_user(session, "alice01")
    with pytest.raises(AuthenticationError) as e1:
        auth.login(session, "ghost01", PW)
    with pytest.raises(AuthenticationError) as e2:
        auth.login(session, "alice01", "Wrong0000")
    assert str(e1.value) == str(e2.value)


@case("UT-AUTH-23", "FR-01", "login: 빈 입력/인젝션 문자열", "AuthenticationError (예외 유형 일관)", "security")
@pytest.mark.parametrize("u,p", [("", ""), ("alice01", ""), ("", PW), ("' OR '1'='1", "x"), ("alice01' --", PW)])
def test_login_bad_inputs(session, u, p):
    factories.make_user(session, "alice01")
    with pytest.raises(AuthenticationError):
        auth.login(session, u, p)


@case("UT-AUTH-24", "FR-01", "get_user: 존재하는 id / 없는 id", "존재하면 User, 없으면 NotFoundError")
def test_get_user(session):
    u = factories.make_user(session, "alice01")
    assert auth.get_user(session, u.id).username == "alice01"
    with pytest.raises(NotFoundError):
        auth.get_user(session, 99999)
