"""단위시험 UT-DASH — SC-02 대시보드 요약 (DashboardService)."""
from datetime import datetime, timedelta

import pytest

from app.errors import NotFoundError
from app.services import dashboard_service as dash
from tests import factories
from tests.case_registry import case

NOW = datetime(2026, 10, 3, 12, 0, 0)


def app_at(session, user, algo="AES", status="submitted", ago=timedelta(0), updated_ago=None):
    a = factories.make_application(session, user, algo, status)
    a.submitted_at = NOW - ago
    a.updated_at = NOW - (updated_ago if updated_ago is not None else ago)
    session.commit()
    return a


@pytest.fixture()
def me(session):
    return factories.make_user(session, "me_user")


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


@case("UT-DASH-01", "FR-03", "get_summary: 본인 신청만 집계", "타인 신청은 total·by_status 에 포함되지 않음")
def test_counts_own_only(session, me):
    other = factories.make_user(session, "other01")
    app_at(session, me, "AES", "approved"); app_at(session, me, "RSA", "submitted")
    app_at(session, other, "HMAC", "approved"); app_at(session, other, "SHA-2", "rejected")
    s = dash.get_summary(session, me.id, NOW)
    assert s["scope"] == "own" and s["applications"]["total"] == 2
    assert s["applications"]["by_status"]["approved"] == 1 and s["applications"]["by_status"]["rejected"] == 0


@case("UT-DASH-02", "FR-03", "get_summary: 진행 중 = 접수 대기 + 심사 중, by_status 는 4개 키 항상 존재", "in_progress 합산, 0건 상태도 0 으로 표기")
def test_in_progress_and_all_status_keys(session, me):
    app_at(session, me, "AES", "submitted"); app_at(session, me, "RSA", "reviewing"); app_at(session, me, "HMAC", "reviewing")
    a = dash.get_summary(session, me.id, NOW)["applications"]
    assert a["in_progress"] == 3
    assert a["by_status"] == {"submitted": 1, "reviewing": 2, "approved": 0, "rejected": 0}


@case("UT-DASH-03", "FR-03", "get_summary: 데이터가 전혀 없는 신규 사용자", "모든 수치 0, 목록·알림 빈 배열, 가명처리 미처리", "boundary")
def test_empty_user(session, me):
    s = dash.get_summary(session, me.id, NOW)
    assert s["applications"] == {"total": 0, "in_progress": 0, "new_last_7d": 0,
                                 "by_status": {"submitted": 0, "reviewing": 0, "approved": 0, "rejected": 0}}
    assert s["certificates"] == {"total": 0, "suspected": 0}
    assert s["recent_applications"] == [] and s["notifications"] == []
    assert s["privacy"] == {"processed": False, "level": None}


@case("UT-DASH-04", "FR-03", "get_summary: 최근 신청은 최신순 최대 3건", "5건 중 최신 3건, 필드 id/algorithm_type/status/status_label/submitted_at(YYYY-MM-DD)")
def test_recent_applications_newest_three(session, me):
    ids = [app_at(session, me, a, "approved", ago=timedelta(days=d)).id
           for a, d in [("AES", 5), ("RSA", 4), ("HMAC", 3), ("SHA-2", 2), ("SHA-3", 1)]]
    rec = dash.get_summary(session, me.id, NOW)["recent_applications"]
    assert [r["id"] for r in rec] == [ids[4], ids[3], ids[2]]
    assert set(rec[0]) == {"id", "algorithm_type", "status", "status_label", "submitted_at"}
    assert rec[0]["submitted_at"] == "2026-10-02" and rec[0]["algorithm_type"] == "SHA-3"


@case("UT-DASH-05", "FR-03", "get_summary: 상태 라벨 매핑", "submitted 접수 대기 / reviewing 시험 진행중 / approved 시험 완료 / rejected 반려")
@pytest.mark.parametrize("status,label", [("submitted", "접수 대기"), ("reviewing", "시험 진행중"), ("approved", "시험 완료"), ("rejected", "반려")])
def test_status_labels(session, me, status, label):
    app_at(session, me, "AES", status)
    assert dash.get_summary(session, me.id, NOW)["recent_applications"][0]["status_label"] == label


@case("UT-DASH-06", "FR-03", "get_summary: 최근 7일 신규 신청 경계", "정확히 7일 전은 포함, 7일 1분 초과는 제외", "boundary")
def test_new_last_7d_boundary(session, me):
    app_at(session, me, "AES", "approved", ago=timedelta(days=6))
    app_at(session, me, "RSA", "approved", ago=timedelta(days=7))
    app_at(session, me, "HMAC", "approved", ago=timedelta(days=7, minutes=1))
    assert dash.get_summary(session, me.id, NOW)["applications"]["new_last_7d"] == 2


@case("UT-DASH-07", "FR-04", "get_summary: 검증서 집계(본인 신청 소속만, 위변조 의심 별도)", "total·suspected 가 본인 건만 반영")
def test_certificate_counts(session, me):
    other = factories.make_user(session, "other01")
    a1 = app_at(session, me, "AES", "approved"); a2 = app_at(session, me, "RSA", "approved")
    factories.make_certificate(session, a1); factories.make_certificate(session, a2, tamper_status="suspected")
    factories.make_certificate(session, app_at(session, other, "HMAC", "approved"), tamper_status="suspected")
    assert dash.get_summary(session, me.id, NOW)["certificates"] == {"total": 2, "suspected": 1}


@case("UT-DASH-08", "FR-02", "get_summary: 가명·익명 처리 상태", "처리 전 processed=False, 처리 후 level 반영")
@pytest.mark.parametrize("level", ["pseudonym", "anonymous"])
def test_privacy_status(session, me, level):
    assert dash.get_summary(session, me.id, NOW)["privacy"] == {"processed": False, "level": None}
    factories.make_personal_info(session, me, level)
    assert dash.get_summary(session, me.id, NOW)["privacy"] == {"processed": True, "level": level}


@case("UT-DASH-09", "FR-05", "get_summary: 위변조 의심 알림이 최우선", "첫 알림이 warning, 메시지에 CV-0000 형식 번호 포함")
def test_notification_suspected_first(session, me):
    app_at(session, me, "RSA", "reviewing")
    c = factories.make_certificate(session, app_at(session, me, "AES", "approved"), tamper_status="suspected")
    n = dash.get_summary(session, me.id, NOW)["notifications"]
    assert n[0] == {"type": "warning", "message": f"검증서(CV-{c.id:04d}) 위변조 의심 항목이 있습니다."}
    assert all(x["type"] == "info" for x in n[1:])


@case("UT-DASH-10", "FR-03", "get_summary: 신청 진행/결과 알림 문구", "reviewing 심사 중 / approved 승인 / rejected 반려, submitted 는 알림 없음")
def test_notification_messages(session, me):
    app_at(session, me, "AES", "submitted", updated_ago=timedelta(days=1))
    app_at(session, me, "RSA", "reviewing", updated_ago=timedelta(days=2))
    app_at(session, me, "HMAC", "approved", updated_ago=timedelta(days=3))
    app_at(session, me, "SHA-2", "rejected", updated_ago=timedelta(days=4))
    msgs = [x["message"] for x in dash.get_summary(session, me.id, NOW)["notifications"]]
    assert msgs == ["RSA 시험이 심사 중입니다.", "HMAC 시험이 승인되었습니다.", "SHA-2 시험이 반려되었습니다."]


@case("UT-DASH-11", "FR-03", "get_summary: 알림은 최대 5건", "8건 발생해도 5건만, 위변조 경고가 잘리지 않음", "boundary")
def test_notifications_capped_at_five(session, me):
    c = factories.make_certificate(session, app_at(session, me, "AES", "approved"), tamper_status="suspected")
    for i in range(7):
        app_at(session, me, "RSA", "reviewing", updated_ago=timedelta(hours=i + 1))
    n = dash.get_summary(session, me.id, NOW)["notifications"]
    assert len(n) == 5 and n[0]["type"] == "warning"


@case("UT-DASH-12", "FR-04", "get_summary: 기관(institution) 사용자는 전체 집계", "scope='all', 타인 신청·검증서 포함, 가명처리는 본인 기준")
def test_institution_scope_all(session):
    officer = factories.make_user(session, "officer01", "institution")
    u1, u2 = factories.make_user(session, "user_a"), factories.make_user(session, "user_b")
    factories.make_certificate(session, app_at(session, u1, "AES", "approved"), tamper_status="suspected")
    app_at(session, u2, "RSA", "submitted")
    s = dash.get_summary(session, officer.id, NOW)
    assert s["scope"] == "all" and s["applications"]["total"] == 2 and s["certificates"] == {"total": 1, "suspected": 1}
    assert s["privacy"] == {"processed": False, "level": None}


@case("UT-DASH-13", "FR-01", "get_summary: 기업 사용자는 개인과 동일하게 본인 범위", "scope='own'")
def test_company_scope_own(session):
    corp = factories.make_user(session, "corp01", "company")
    app_at(session, factories.make_user(session, "other01"), "AES", "approved")
    s = dash.get_summary(session, corp.id, NOW)
    assert s["scope"] == "own" and s["applications"]["total"] == 0


@case("UT-DASH-14", "FR-01", "get_summary: 없는 사용자", "NotFoundError", "negative")
def test_unknown_user(session):
    with pytest.raises(NotFoundError):
        dash.get_summary(session, 99999, NOW)


@case("UT-DASH-15", "FR-01", "get_summary: 사용자 정보에 username/user_type 만, 민감 필드 없음", "결과 전체에 password/hash 키 없음", "security")
def test_no_sensitive_fields(session, me):
    s = dash.get_summary(session, me.id, NOW)
    assert s["user"] == {"username": "me_user", "user_type": "individual"}
    assert not any("password" in k or "hash" in k for k in keys_deep(s))


@case("UT-DASH-16", "FR-03", "get_summary: 타인 신청이 최근 목록·알림에 노출되지 않음", "타인 신청의 알고리즘/상태가 결과에 없음", "security")
def test_other_users_not_leaked(session, me):
    other = factories.make_user(session, "other01")
    app_at(session, other, "ECDSA", "reviewing"); factories.make_certificate(session, app_at(session, other, "DRBG", "approved"), tamper_status="suspected")
    s = dash.get_summary(session, me.id, NOW)
    text = str(s["recent_applications"]) + str(s["notifications"])
    assert "ECDSA" not in text and "DRBG" not in text and s["notifications"] == []
