"""단위시험 UT-SEED — 초기 데이터 적재(시스템설계서 v1.1 5.3절, D12)."""
from sqlalchemy import func, select

from app.models import CavpApplication, Certificate, PersonalInfo, User
from app.seed import seed
from app.services import auth_service
from tests.case_registry import case


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


@case("UT-SEED-01", "FR-01", "seed: 사용자 3종 생성", "individual/company/institution 각 1명, 기업·기관은 org_code 보유")
def test_seed_users(session):
    seed(session)
    users = {u.username: u for u in session.scalars(select(User))}
    assert {u.user_type for u in users.values()} == {"individual", "company", "institution"}
    assert users["demo_company"].org_code and users["demo_institution"].org_code


@case("UT-SEED-02", "FR-01", "seed: 데모 계정 비밀번호는 해시로 저장되고 로그인 가능", "평문 미저장, login('demo_individual','Demo1234') 성공", "security")
def test_seed_passwords_hashed(session):
    seed(session)
    for u in session.scalars(select(User)):
        assert u.password_hash.startswith("$2") and "Demo1234" not in u.password_hash
    assert auth_service.login(session, "demo_individual", "Demo1234").username == "demo_individual"


@case("UT-SEED-03", "FR-03", "seed: 신청 4건 이상, 4개 상태 모두 포함", "submitted/reviewing/approved/rejected 각 1건 이상")
def test_seed_applications(session):
    seed(session)
    statuses = {a.status for a in session.scalars(select(CavpApplication))}
    assert statuses == {"submitted", "reviewing", "approved", "rejected"}


@case("UT-SEED-04", "FR-04", "seed: 검증서 3건 중 1건은 위변조 의심", "certificates=3, tamper_status='suspected' 정확히 1건")
def test_seed_certificates(session):
    seed(session)
    certs = list(session.scalars(select(Certificate)))
    assert len(certs) == 3 and sum(c.tamper_status == "suspected" for c in certs) == 1
    approved_ids = {a.id for a in session.scalars(select(CavpApplication).where(CavpApplication.status == "approved"))}
    assert all(c.application_id in approved_ids for c in certs)


@case("UT-SEED-05", "FR-02", "seed: 개인정보는 가명/익명 처리값만 적재", "personal_info 가 존재하고 원본 이름 형태(마스킹 없는 값) 없음", "security")
def test_seed_personal_info_masked(session):
    seed(session)
    rows = list(session.scalars(select(PersonalInfo)))
    assert rows and all("*" in r.masked_display_value or r.masked_display_value == "익명" for r in rows)


@case("UT-SEED-06", "FR-01", "seed: 멱등 — 두 번 실행해도 건수 불변", "2회 실행 후 건수 동일, 반환 dict 의 건수와 실제 건수 일치", "boundary")
def test_seed_idempotent(session):
    r1 = seed(session)
    before = {m: count(session, m) for m in (User, PersonalInfo, CavpApplication, Certificate)}
    r2 = seed(session)
    after = {m: count(session, m) for m in before}
    assert before == after and r1 == r2
    assert r1 == {"users": before[User], "personal_info": before[PersonalInfo],
                  "applications": before[CavpApplication], "certificates": before[Certificate]}
