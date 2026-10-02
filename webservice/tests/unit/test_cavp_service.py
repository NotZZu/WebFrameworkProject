"""단위시험 UT-CAVP — FR-03 CAVP 시험 신청/조회 (CavpApplicationService)."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.errors import (DuplicateApplicationError, InvalidTransitionError, NotFoundError,
                        PermissionDeniedError, ValidationError)
from app.models import CavpApplication
from app.services import cavp_service as cavp
from tests import factories
from tests.case_registry import case


def n_apps(session):
    return session.scalar(select(func.count()).select_from(CavpApplication))


@pytest.fixture()
def person(session):
    return factories.make_user(session, "person01")


@pytest.fixture()
def officer(session):
    return factories.make_user(session, "officer01", "institution")


# ---------- create ----------
@case("UT-CAVP-01", "FR-03", "create_application: 유효한 알고리즘", "status='submitted', submitted_at 설정, 본인 소유")
def test_create_ok(session, person):
    a = cavp.create_application(session, person.id, "AES")
    assert a.status == "submitted" and a.user_id == person.id and a.submitted_at is not None


@case("UT-CAVP-02", "FR-03", "create_application: 허용 알고리즘 전체", "ALGORITHMS 의 모든 값 신청 가능")
@pytest.mark.parametrize("algo", cavp.ALGORITHMS)
def test_create_each_algorithm(session, person, algo):
    assert cavp.create_application(session, person.id, algo).algorithm_type == algo


@case("UT-CAVP-03", "FR-03", "create_application: 빈 값/미허용 알고리즘", "ValidationError, 레코드 미생성", "negative")
@pytest.mark.parametrize("algo", ["", "   ", None, "aes", "MD5", "AES; DROP TABLE x"])
def test_create_invalid_algorithm(session, person, algo):
    with pytest.raises(ValidationError):
        cavp.create_application(session, person.id, algo)
    assert n_apps(session) == 0


@case("UT-CAVP-04", "FR-03", "create_application: 없는 사용자", "NotFoundError", "negative")
def test_create_unknown_user(session):
    with pytest.raises(NotFoundError):
        cavp.create_application(session, 99999, "AES")


@case("UT-CAVP-05", "FR-03", "create_application: 진행 중 동일 알고리즘 중복 신청", "DuplicateApplicationError (submitted/reviewing 모두)", "negative")
@pytest.mark.parametrize("status", ["submitted", "reviewing"])
def test_create_duplicate_active(session, person, status):
    factories.make_application(session, person, "AES", status)
    with pytest.raises(DuplicateApplicationError):
        cavp.create_application(session, person.id, "AES")
    assert n_apps(session) == 1


@case("UT-CAVP-06", "FR-03", "create_application: 종료(approved/rejected) 후 재신청 및 타 알고리즘/타 사용자 신청", "허용", "boundary")
@pytest.mark.parametrize("status", ["approved", "rejected"])
def test_create_allowed_cases(session, person, status):
    factories.make_application(session, person, "AES", status)
    cavp.create_application(session, person.id, "AES")                      # 종료 후 재신청
    cavp.create_application(session, person.id, "RSA")                      # 다른 알고리즘
    other = factories.make_user(session, "person02")
    cavp.create_application(session, other.id, "AES")                       # 다른 사용자
    assert n_apps(session) == 4


# ---------- update_status ----------
@case("UT-CAVP-07", "FR-03", "update_status: 허용 전이 3종", "submitted→reviewing, reviewing→approved, reviewing→rejected", )
@pytest.mark.parametrize("src,dst", [("submitted", "reviewing"), ("reviewing", "approved"), ("reviewing", "rejected")])
def test_transition_allowed(session, person, officer, src, dst):
    a = factories.make_application(session, person, "AES", src)
    assert cavp.update_status(session, officer.id, a.id, dst).status == dst
    assert session.get(CavpApplication, a.id).status == dst


@case("UT-CAVP-08", "FR-03", "update_status: 허용되지 않는 전이 전수(허용 3개 제외 13개)", "InvalidTransitionError, 상태 불변", "negative")
@pytest.mark.parametrize("src", cavp.STATUSES)
@pytest.mark.parametrize("dst", cavp.STATUSES)
def test_transition_forbidden(session, person, officer, src, dst):
    if dst in cavp.TRANSITIONS[src]:
        pytest.skip("허용 전이는 UT-CAVP-07")
    a = factories.make_application(session, person, "AES", src)
    with pytest.raises(InvalidTransitionError):
        cavp.update_status(session, officer.id, a.id, dst)
    assert session.get(CavpApplication, a.id).status == src


@case("UT-CAVP-09", "FR-03", "update_status: 존재하지 않는 상태값", "ValidationError", "negative")
@pytest.mark.parametrize("dst", ["", "done", "APPROVED", None])
def test_transition_unknown_status(session, person, officer, dst):
    a = factories.make_application(session, person, "AES", "submitted")
    with pytest.raises(ValidationError):
        cavp.update_status(session, officer.id, a.id, dst)


@case("UT-CAVP-10", "FR-03", "update_status: 전이 시 updated_at 갱신", "updated_at 이 이전보다 이후", "boundary")
def test_transition_touches_updated_at(session, person, officer):
    a = factories.make_application(session, person, "AES", "submitted")
    a.updated_at = a.updated_at - timedelta(days=1)
    session.commit()
    before = a.updated_at
    cavp.update_status(session, officer.id, a.id, "reviewing")
    assert session.get(CavpApplication, a.id).updated_at > before


@case("UT-CAVP-11", "FR-03", "update_status: institution 이 아닌 사용자는 상태 변경 불가", "PermissionDeniedError, 상태 불변", "security")
@pytest.mark.parametrize("utype", ["individual", "company"])
def test_transition_requires_institution(session, person, utype):
    actor = factories.make_user(session, f"actor_{utype}", utype)
    a = factories.make_application(session, person, "AES", "submitted")
    with pytest.raises(PermissionDeniedError):
        cavp.update_status(session, actor.id, a.id, "reviewing")
    assert session.get(CavpApplication, a.id).status == "submitted"


@case("UT-CAVP-12", "FR-03", "update_status: 없는 신청/없는 사용자", "NotFoundError", "negative")
def test_transition_not_found(session, person, officer):
    with pytest.raises(NotFoundError):
        cavp.update_status(session, officer.id, 99999, "reviewing")
    a = factories.make_application(session, person, "AES", "submitted")
    with pytest.raises(NotFoundError):
        cavp.update_status(session, 99999, a.id, "reviewing")


# ---------- list / get ----------
@case("UT-CAVP-13", "FR-03", "list_applications: 본인 신청만, 최신순", "타인 신청 제외, submitted_at 내림차순")
def test_list_own_only_newest_first(session, person):
    other = factories.make_user(session, "person02")
    a1 = factories.make_application(session, person, "AES")
    a2 = factories.make_application(session, person, "RSA")
    factories.make_application(session, other, "HMAC")
    a1.submitted_at -= timedelta(days=2); a2.submitted_at -= timedelta(days=1); session.commit()
    res = cavp.list_applications(session, person.id)
    assert [x.id for x in res["items"]] == [a2.id, a1.id] and res["total"] == 2


@case("UT-CAVP-14", "FR-03", "list_applications: 상태 필터", "해당 상태만 반환, total 도 필터 기준")
def test_list_status_filter(session, person):
    factories.make_application(session, person, "AES", "approved")
    factories.make_application(session, person, "RSA", "submitted")
    res = cavp.list_applications(session, person.id, status="approved")
    assert res["total"] == 1 and res["items"][0].status == "approved"


@case("UT-CAVP-15", "FR-03", "list_applications: 잘못된 상태 필터", "ValidationError", "negative")
def test_list_bad_status_filter(session, person):
    with pytest.raises(ValidationError):
        cavp.list_applications(session, person.id, status="weird")


@case("UT-CAVP-16", "FR-03", "list_applications: 페이지네이션 (25건, per_page=10)", "1p 10건, 2p 10건, 3p 5건, 4p 0건, total=25", "boundary")
def test_list_pagination(session, person):
    for i in range(25):
        a = factories.make_application(session, person, "AES", "approved")
    sizes = [len(cavp.list_applications(session, person.id, page=p, per_page=10)["items"]) for p in (1, 2, 3, 4)]
    assert sizes == [10, 10, 5, 0]
    assert cavp.list_applications(session, person.id, page=1, per_page=10)["total"] == 25


@case("UT-CAVP-17", "FR-03", "list_applications: page/per_page 경계값", "page 0·per_page 0/51 → ValidationError, per_page 1/50 허용", "boundary")
@pytest.mark.parametrize("page,per_page,ok", [(0, 10, False), (-1, 10, False), (1, 0, False), (1, 51, False), (1, 1, True), (1, 50, True)])
def test_list_bounds(session, person, page, per_page, ok):
    if ok:
        assert cavp.list_applications(session, person.id, page=page, per_page=per_page)["per_page"] == per_page
    else:
        with pytest.raises(ValidationError):
            cavp.list_applications(session, person.id, page=page, per_page=per_page)


@case("UT-CAVP-18", "FR-03", "list_applications: 신청이 없으면 빈 목록", "items=[], total=0")
def test_list_empty(session, person):
    assert cavp.list_applications(session, person.id) == {"items": [], "total": 0, "page": 1, "per_page": 10}


@case("UT-CAVP-19", "FR-03", "get_application: 본인 / 타인 / 없는 id", "본인 반환, 타인 PermissionDeniedError, 없는 id NotFoundError")
def test_get_application_access(session, person):
    other = factories.make_user(session, "person02")
    a = factories.make_application(session, person, "AES")
    assert cavp.get_application(session, person.id, a.id).id == a.id
    with pytest.raises(PermissionDeniedError):
        cavp.get_application(session, other.id, a.id)
    with pytest.raises(NotFoundError):
        cavp.get_application(session, person.id, 99999)


@case("UT-CAVP-20", "FR-03", "get_application: institution 은 모든 신청 조회 가능", "타인 신청도 반환", "boundary")
def test_get_application_institution_can_view_all(session, person, officer):
    a = factories.make_application(session, person, "AES")
    assert cavp.get_application(session, officer.id, a.id).id == a.id
