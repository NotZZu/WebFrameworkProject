"""단위시험 UT-CERT — FR-04 검증서 이력 조회 / FR-05 위변조 탐지 모의 (CertificateService)."""
import hashlib
import os
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.errors import (DuplicateApplicationError, InvalidTransitionError, NotFoundError,
                        PermissionDeniedError, ValidationError)
from app.models import Certificate
from app.services import certificate_service as cert
from tests import factories
from tests.case_registry import case

CONTENT = b"CAVP certificate body v1"
SHA = hashlib.sha256(CONTENT).hexdigest()


@pytest.fixture()
def person(session):
    return factories.make_user(session, "person01")


@pytest.fixture()
def officer(session):
    return factories.make_user(session, "officer01", "institution")


@pytest.fixture()
def approved_app(session, person):
    return factories.make_application(session, person, "AES", "approved")


def n_certs(session):
    return session.scalar(select(func.count()).select_from(Certificate))


# ---------- hash ----------
@case("UT-CERT-01", "FR-05", "compute_hash: SHA-256 hex", "표준 SHA-256 과 동일한 64자 소문자 hex")
def test_compute_hash():
    assert cert.compute_hash(CONTENT) == SHA and len(SHA) == 64


@case("UT-CERT-02", "FR-05", "compute_hash: 1바이트 차이 / 빈 입력", "1바이트만 달라도 해시 상이, 빈 바이트도 처리", "boundary")
def test_compute_hash_sensitivity():
    assert cert.compute_hash(CONTENT) != cert.compute_hash(CONTENT + b"x")
    assert cert.compute_hash(b"") == hashlib.sha256(b"").hexdigest()


@case("UT-CERT-03", "FR-05", "compare_hash: 동일 해시", "'normal'")
def test_compare_hash_same():
    assert cert.compare_hash(SHA, SHA) == "normal"


@case("UT-CERT-04", "FR-05", "compare_hash: 상이한 해시", "'suspected'", "negative")
def test_compare_hash_diff():
    assert cert.compare_hash(SHA, cert.compute_hash(b"tampered")) == "suspected"


@case("UT-CERT-05", "FR-05", "compare_hash: 대소문자만 다른 hex", "동일 값으로 보고 'normal'", "boundary")
def test_compare_hash_case_insensitive():
    assert cert.compare_hash(SHA, SHA.upper()) == "normal"


# ---------- issue ----------
@case("UT-CERT-06", "FR-04", "issue_certificate: 승인된 신청에 발급", "integrity_hash=SHA-256(내용), tamper_status='normal', 파일 저장")
def test_issue_ok(session, officer, approved_app, tmp_path):
    c = cert.issue_certificate(session, officer.id, approved_app.id, "CAVP", CONTENT, str(tmp_path))
    assert c.integrity_hash == SHA and c.tamper_status == "normal" and c.cert_type == "CAVP"
    assert os.path.exists(tmp_path / f"cert_{c.id}.bin")
    assert (tmp_path / f"cert_{c.id}.bin").read_bytes() == CONTENT


@case("UT-CERT-07", "FR-04", "issue_certificate: 승인 이전/반려 상태", "InvalidTransitionError, 검증서 미생성", "negative")
@pytest.mark.parametrize("status", ["submitted", "reviewing", "rejected"])
def test_issue_requires_approved(session, officer, person, status, tmp_path):
    a = factories.make_application(session, person, "AES", status)
    with pytest.raises(InvalidTransitionError):
        cert.issue_certificate(session, officer.id, a.id, "CAVP", CONTENT, str(tmp_path))
    assert n_certs(session) == 0


@case("UT-CERT-08", "FR-04", "issue_certificate: 신청당 1건(중복 발급)", "DuplicateApplicationError", "negative")
def test_issue_duplicate(session, officer, approved_app, tmp_path):
    cert.issue_certificate(session, officer.id, approved_app.id, "CAVP", CONTENT, str(tmp_path))
    with pytest.raises(DuplicateApplicationError):
        cert.issue_certificate(session, officer.id, approved_app.id, "CAVP", CONTENT, str(tmp_path))
    assert n_certs(session) == 1


@case("UT-CERT-09", "FR-04", "issue_certificate: institution 이 아니면 발급 불가", "PermissionDeniedError", "security")
@pytest.mark.parametrize("utype", ["individual", "company"])
def test_issue_requires_institution(session, approved_app, utype, tmp_path):
    actor = factories.make_user(session, f"a_{utype}", utype)
    with pytest.raises(PermissionDeniedError):
        cert.issue_certificate(session, actor.id, approved_app.id, "CAVP", CONTENT, str(tmp_path))
    assert n_certs(session) == 0


@case("UT-CERT-10", "FR-04", "issue_certificate: 잘못된 cert_type / 빈 내용 / 없는 신청", "ValidationError / ValidationError / NotFoundError", "negative")
def test_issue_invalid_inputs(session, officer, approved_app, tmp_path):
    with pytest.raises(ValidationError):
        cert.issue_certificate(session, officer.id, approved_app.id, "XYZ", CONTENT, str(tmp_path))
    with pytest.raises(ValidationError):
        cert.issue_certificate(session, officer.id, approved_app.id, "CAVP", b"", str(tmp_path))
    with pytest.raises(NotFoundError):
        cert.issue_certificate(session, officer.id, 99999, "CAVP", CONTENT, str(tmp_path))
    assert n_certs(session) == 0


@case("UT-CERT-11", "FR-04", "issue_certificate: KCMVP 유형도 발급", "cert_type='KCMVP'", "boundary")
def test_issue_kcmvp(session, officer, approved_app, tmp_path):
    assert cert.issue_certificate(session, officer.id, approved_app.id, "KCMVP", CONTENT, str(tmp_path)).cert_type == "KCMVP"


# ---------- list / get ----------
@case("UT-CERT-12", "FR-04", "list_certificates: 본인 신청 소속만, 최신 발급순", "타인 검증서 제외, issued_at 내림차순")
def test_list_own_newest_first(session, person):
    other = factories.make_user(session, "person02")
    c1 = factories.make_certificate(session, factories.make_application(session, person, "AES", "approved"))
    c2 = factories.make_certificate(session, factories.make_application(session, person, "RSA", "approved"))
    factories.make_certificate(session, factories.make_application(session, other, "HMAC", "approved"))
    c1.issued_at -= timedelta(days=3); c2.issued_at -= timedelta(days=1); session.commit()
    res = cert.list_certificates(session, person.id)
    assert [c.id for c in res["items"]] == [c2.id, c1.id] and res["total"] == 2


@case("UT-CERT-13", "FR-04", "list_certificates: 페이지네이션/경계/빈 목록", "per_page 1~50, page>=1, 빈 목록은 total=0", "boundary")
def test_list_pagination_and_bounds(session, person):
    assert cert.list_certificates(session, person.id)["total"] == 0
    for _ in range(3):
        factories.make_certificate(session, factories.make_application(session, person, "AES", "approved"))
    assert len(cert.list_certificates(session, person.id, page=2, per_page=2)["items"]) == 1
    for page, per in [(0, 10), (1, 0), (1, 51)]:
        with pytest.raises(ValidationError):
            cert.list_certificates(session, person.id, page=page, per_page=per)


@case("UT-CERT-14", "FR-04", "get_certificate: 본인 / 타인 / 없는 id", "본인 반환, 타인 PermissionDeniedError, 없는 id NotFoundError")
def test_get_certificate_access(session, person):
    other = factories.make_user(session, "person02")
    c = factories.make_certificate(session, factories.make_application(session, person, "AES", "approved"))
    assert cert.get_certificate(session, person.id, c.id).id == c.id
    with pytest.raises(PermissionDeniedError):
        cert.get_certificate(session, other.id, c.id)
    with pytest.raises(NotFoundError):
        cert.get_certificate(session, person.id, 99999)


# ---------- verify_integrity ----------
@case("UT-CERT-15", "FR-05", "verify_integrity: 파일 무결 → normal", "tamper_status='normal'")
def test_verify_normal(session, officer, approved_app, tmp_path):
    c = cert.issue_certificate(session, officer.id, approved_app.id, "CAVP", CONTENT, str(tmp_path))
    assert cert.verify_integrity(session, c.id, str(tmp_path)).tamper_status == "normal"


@case("UT-CERT-16", "FR-05", "verify_integrity: 파일 변조 → suspected(DB 에도 반영)", "반환값과 DB 의 tamper_status 모두 'suspected'")
def test_verify_tampered_persisted(session, officer, approved_app, tmp_path):
    c = cert.issue_certificate(session, officer.id, approved_app.id, "CAVP", CONTENT, str(tmp_path))
    (tmp_path / f"cert_{c.id}.bin").write_bytes(CONTENT + b" tampered")
    assert cert.verify_integrity(session, c.id, str(tmp_path)).tamper_status == "suspected"
    assert session.get(Certificate, c.id).tamper_status == "suspected"


@case("UT-CERT-17", "FR-05", "verify_integrity: 파일 삭제/누락 → suspected", "'suspected' (예외 아님)", "negative")
def test_verify_missing_file(session, officer, approved_app, tmp_path):
    c = cert.issue_certificate(session, officer.id, approved_app.id, "CAVP", CONTENT, str(tmp_path))
    os.remove(tmp_path / f"cert_{c.id}.bin")
    assert cert.verify_integrity(session, c.id, str(tmp_path)).tamper_status == "suspected"


@case("UT-CERT-18", "FR-05", "verify_integrity: 원복 후 재검증 시 normal", "변조 → suspected, 원복 → normal", "boundary")
def test_verify_restored(session, officer, approved_app, tmp_path):
    c = cert.issue_certificate(session, officer.id, approved_app.id, "CAVP", CONTENT, str(tmp_path))
    f = tmp_path / f"cert_{c.id}.bin"
    f.write_bytes(b"bad"); assert cert.verify_integrity(session, c.id, str(tmp_path)).tamper_status == "suspected"
    f.write_bytes(CONTENT); assert cert.verify_integrity(session, c.id, str(tmp_path)).tamper_status == "normal"


@case("UT-CERT-19", "FR-05", "verify_integrity: 존재하지 않는 cert_id", "NotFoundError", "negative")
def test_verify_not_found(session, tmp_path):
    with pytest.raises(NotFoundError):
        cert.verify_integrity(session, 99999, str(tmp_path))


@case("UT-CERT-20", "FR-05", "verify_integrity: 저장된 integrity_hash 자체는 변경하지 않음", "검증 후에도 integrity_hash 불변", "security")
def test_verify_does_not_rewrite_hash(session, officer, approved_app, tmp_path):
    c = cert.issue_certificate(session, officer.id, approved_app.id, "CAVP", CONTENT, str(tmp_path))
    (tmp_path / f"cert_{c.id}.bin").write_bytes(b"tampered")
    cert.verify_integrity(session, c.id, str(tmp_path))
    assert session.get(Certificate, c.id).integrity_hash == SHA


@case("UT-CERT-21", "FR-05", "verify_integrity: 시드처럼 이미 suspected 인 건(파일 없음)", "파일이 없으면 suspected 유지", "boundary")
def test_verify_seeded_suspected(session, person, tmp_path):
    c = factories.make_certificate(session, factories.make_application(session, person, "AES", "approved"),
                                   tamper_status="suspected")
    assert cert.verify_integrity(session, c.id, str(tmp_path)).tamper_status == "suspected"
