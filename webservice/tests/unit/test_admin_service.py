"""단위시험 UT-ADM — SC-08 관리자 대시보드 요약 (AdminService)."""
from datetime import datetime, timedelta

import pytest

from app.errors import NotFoundError, PermissionDeniedError
from app.services import admin_service as admin
from app.services.cavp_service import ALGORITHMS
from tests import factories
from tests.case_registry import case

NOW = datetime(2026, 11, 9, 12, 0, 0)


def app_at(session, user, algo="AES", status="submitted", ago=timedelta(0)):
    a = factories.make_application(session, user, algo, status)
    a.submitted_at = NOW - ago
    a.updated_at = NOW - ago
    session.commit()
    return a


@pytest.fixture()
def officer(session):
    return factories.make_user(session, "officer01", "institution")


@pytest.fixture()
def person(session):
    return factories.make_user(session, "person01")


def keys_deep(d):
    out = set()
    for k, v in d.items():
        out.add(k)
        if isinstance(v, dict):
            out |= keys_deep(v)
        if isinstance(v, list):
            for x in v:
                if isinstance(x, dict):
                    out |= keys_deep(x)
    return out


@case("UT-ADM-01", "FR-06", "get_summary: 모든 사용자의 신청을 집계", "타인 신청 포함 total·by_status·in_progress·pending_review 계산")
def test_counts_everyone(session, officer, person):
    other = factories.make_user(session, "person02")
    app_at(session, person, "AES", "submitted"); app_at(session, person, "RSA", "reviewing")
    app_at(session, other, "AES", "approved"); app_at(session, other, "HMAC", "rejected")
    app_at(session, other, "SHA-2", "cancelled")
    a = admin.get_summary(session, officer.id, NOW)["applications"]
    assert a["total"] == 5 and a["in_progress"] == 2 and a["pending_review"] == 1
    assert a["by_status"] == {"submitted": 1, "reviewing": 1, "approved": 1, "rejected": 1, "cancelled": 1}


@case("UT-ADM-02", "FR-06", "get_summary: 알고리즘별 건수는 7개 키가 항상 존재", "신청 없는 알고리즘도 0 으로 표기, 취소 건도 포함", "boundary")
def test_by_algorithm_all_keys(session, officer, person):
    app_at(session, person, "AES", "approved"); app_at(session, person, "AES", "cancelled"); app_at(session, person, "RSA", "submitted")
    by = admin.get_summary(session, officer.id, NOW)["applications"]["by_algorithm"]
    assert set(by) == set(ALGORITHMS) and by["AES"] == 2 and by["RSA"] == 1 and by["DRBG"] == 0


@case("UT-ADM-03", "FR-06", "get_summary: 데이터가 전혀 없을 때", "모든 수치 0, 목록·주의 사항 빈 배열", "boundary")
def test_empty(session, officer):
    s = admin.get_summary(session, officer.id, NOW)
    assert s["applications"]["total"] == 0 and s["applications"]["in_progress"] == 0
    assert s["applications"]["pending_review"] == 0 and s["applications"]["new_last_7d"] == 0
    assert set(s["applications"]["by_status"].values()) == {0}
    assert s["certificates"] == {"total": 0, "suspected": 0}
    assert s["recent_applications"] == [] and s["attention"] == []


@case("UT-ADM-04", "FR-06", "get_summary: 최근 7일 신청 수 경계", "정확히 7일 전은 포함, 7일 1초 전은 제외", "boundary")
def test_new_last_7d_boundary(session, officer, person):
    app_at(session, person, "AES", "submitted", ago=timedelta(days=7))
    app_at(session, person, "RSA", "submitted", ago=timedelta(days=7, seconds=1))
    assert admin.get_summary(session, officer.id, NOW)["applications"]["new_last_7d"] == 1


@case("UT-ADM-05", "FR-06", "get_summary: 검증서 수와 위변조 의심", "total·suspected 집계(전체 사용자 기준)")
def test_certificates(session, officer, person):
    other = factories.make_user(session, "person02")
    a1 = app_at(session, person, "AES", "approved"); a2 = app_at(session, other, "RSA", "approved"); a3 = app_at(session, other, "HMAC", "approved")
    factories.make_certificate(session, a1); factories.make_certificate(session, a2, tamper_status="suspected")
    factories.make_certificate(session, a3, tamper_status="suspected")
    assert admin.get_summary(session, officer.id, NOW)["certificates"] == {"total": 3, "suspected": 2}


@case("UT-ADM-06", "FR-06", "get_summary: 최근 신청은 최신순 최대 5건, 신청자와 상태 이름 포함", "6건 중 5건, submitted_at 내림차순, owner=아이디, status_label 한글")
def test_recent_applications(session, officer, person):
    for i, algo in enumerate(ALGORITHMS[:6]):
        app_at(session, person, algo, "submitted", ago=timedelta(hours=i))
    rows = admin.get_summary(session, officer.id, NOW)["recent_applications"]
    assert len(rows) == 5 and [r["algorithm_type"] for r in rows] == list(ALGORITHMS[:5])
    assert rows[0]["owner"] == "person01" and rows[0]["status_label"] == "접수 대기"
    assert {"id", "algorithm_type", "owner", "status", "status_label", "submitted_at"} == set(rows[0])


@case("UT-ADM-07", "FR-06", "get_summary: 주의 사항", "의심 검증서마다 warning(번호 4자리), 심사 대기가 있으면 info 한 건, warning 이 먼저")
def test_attention(session, officer, person):
    a1 = app_at(session, person, "AES", "approved"); app_at(session, person, "RSA", "submitted"); app_at(session, person, "HMAC", "submitted")
    c = factories.make_certificate(session, a1, tamper_status="suspected")
    att = admin.get_summary(session, officer.id, NOW)["attention"]
    assert att[0] == {"type": "warning", "message": f"검증서(CV-{c.id:04d}) 위변조 의심 항목이 있습니다."}
    assert att[1] == {"type": "info", "message": "심사를 기다리는 신청이 2건 있습니다."} and len(att) == 2


@case("UT-ADM-08", "FR-06", "get_summary: 주의 사항은 최대 5건", "의심 검증서가 7건이어도 5건까지만", "boundary")
def test_attention_capped(session, officer, person):
    for algo in ALGORITHMS:
        a = app_at(session, person, algo, "approved")
        factories.make_certificate(session, a, tamper_status="suspected")
    assert len(admin.get_summary(session, officer.id, NOW)["attention"]) == 5


@case("UT-ADM-09", "FR-06", "get_summary: 기관이 아닌 사용자", "PermissionDeniedError (개인·기업 모두)", "security")
@pytest.mark.parametrize("user_type", ["individual", "company"])
def test_non_institution_denied(session, user_type):
    u = factories.make_user(session, f"{user_type}01", user_type)
    with pytest.raises(PermissionDeniedError):
        admin.get_summary(session, u.id, NOW)


@case("UT-ADM-10", "FR-06", "get_summary: 없는 사용자", "NotFoundError", "negative")
def test_unknown_user(session):
    with pytest.raises(NotFoundError):
        admin.get_summary(session, 99999, NOW)


@case("UT-ADM-11", "FR-06", "get_summary: 민감 정보 비노출", "응답 어디에도 비밀번호 해시·무결성 해시·원본 내용 키가 없음", "security")
def test_no_sensitive_keys(session, officer, person):
    a = app_at(session, person, "AES", "approved"); factories.make_certificate(session, a, tamper_status="suspected")
    keys = keys_deep(admin.get_summary(session, officer.id, NOW))
    assert not {"password_hash", "password", "integrity_hash", "content", "pseudonym_id"} & keys
