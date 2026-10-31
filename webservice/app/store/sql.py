"""SQLAlchemy 구현. 기존 서비스 코드의 질의를 그대로 옮겼다."""
import os
import pathlib

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from ..errors import DuplicateApplicationError, DuplicateUsernameError
from ..models import ActiveSession, CavpApplication, Certificate, PersonalInfo, User, utcnow
from .base import Store


_MAX_ID = 2**63 - 1  # DB 정수 한도. 넘는 번호는 '없는 번호'로 취급한다(DF-16: 넘으면 DB 드라이버 오류로 500)


def _valid_id(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= _MAX_ID


class SqlStore(Store):
    def __init__(self, session):
        self.session = session

    # ---- 사용자 ----
    def get_user(self, user_id):
        return self.session.get(User, user_id) if _valid_id(user_id) else None

    def get_user_by_username(self, username):
        return self.session.scalar(select(User).where(User.username == username))

    def add_user(self, username, password_hash, user_type, org_code):
        user = User(username=username, password_hash=password_hash, user_type=user_type, org_code=org_code)
        self.session.add(user)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise DuplicateUsernameError("이미 사용 중인 아이디입니다.")
        return user

    def get_users_by_ids(self, ids) -> dict:
        ids = set(ids)
        if not ids:
            return {}
        return {u.id: u for u in self.session.scalars(select(User).where(User.id.in_(ids)))}

    # ---- 로그인 세션 ----
    def add_session(self, sid, user_id):
        self.session.add(ActiveSession(sid=sid, user_id=user_id))
        self.session.commit()

    def get_session(self, sid):
        return self.session.get(ActiveSession, sid)

    def delete_session(self, sid):
        row = self.session.get(ActiveSession, sid)
        if row:
            self.session.delete(row)
            self.session.commit()

    # ---- 시험 신청 ----
    def create_application(self, user_id, algorithm_type):
        active = self.session.scalar(
            select(func.count()).select_from(CavpApplication).where(
                CavpApplication.user_id == user_id,
                CavpApplication.algorithm_type == algorithm_type,
                CavpApplication.status.in_(("submitted", "reviewing"))))
        if active:
            raise DuplicateApplicationError("같은 알고리즘의 진행 중인 신청이 있습니다.")
        app = CavpApplication(user_id=user_id, algorithm_type=algorithm_type, status="submitted")
        self.session.add(app)
        try:
            self.session.commit()
        except IntegrityError:  # 동시에 들어온 같은 신청이 먼저 저장됨 — DB 의 부분 유일 인덱스가 막았다(DF-13)
            self.session.rollback()
            raise DuplicateApplicationError("같은 알고리즘의 진행 중인 신청이 있습니다.")
        return app

    def get_application(self, application_id):
        return self.session.get(CavpApplication, application_id) if _valid_id(application_id) else None

    def change_application_status(self, application_id, expected_status, new_status) -> bool:
        # '내가 읽은 상태일 때만' 바꾸는 한 번의 UPDATE (DF-14)
        changed = self.session.execute(
            update(CavpApplication)
            .where(CavpApplication.id == application_id, CavpApplication.status == expected_status)
            .values(status=new_status, updated_at=utcnow())).rowcount
        self.session.commit()
        obj = self.session.get(CavpApplication, application_id)
        if obj is not None:
            self.session.refresh(obj)
        return changed == 1

    def list_applications(self, user_id, status, page, per_page):
        cond = [] if user_id is None else [CavpApplication.user_id == user_id]
        if status is not None:
            cond.append(CavpApplication.status == status)
        total = self.session.scalar(select(func.count()).select_from(CavpApplication).where(*cond))
        items = self.session.scalars(
            select(CavpApplication).where(*cond)
            .order_by(CavpApplication.submitted_at.desc(), CavpApplication.id.desc())
            .limit(per_page).offset((page - 1) * per_page)).all()
        return list(items), total

    def all_applications(self, user_id):
        q = select(CavpApplication)
        if user_id is not None:
            q = q.where(CavpApplication.user_id == user_id)
        return list(self.session.scalars(q))

    # ---- 검증서·가명정보 ----
    def list_certificates(self, user_id):
        q = select(Certificate)
        if user_id is not None:
            q = q.join(CavpApplication, Certificate.application_id == CavpApplication.id) \
                .where(CavpApplication.user_id == user_id)
        return list(self.session.scalars(q))

    def get_personal_info(self, user_id):
        return self.session.scalar(select(PersonalInfo).where(PersonalInfo.user_id == user_id))

    def create_certificate(self, application_id, cert_type, integrity_hash, content, storage_dir):
        cert = Certificate(application_id=application_id, cert_type=cert_type, integrity_hash=integrity_hash,
                           tamper_status="normal")
        self.session.add(cert)
        try:
            self.session.commit()
        except IntegrityError:  # 같은 신청에 동시에 발급되면 DB 의 유일 제약이 한 건만 남긴다
            self.session.rollback()
            raise DuplicateApplicationError("이미 검증서가 발급된 신청입니다.")
        try:
            directory = pathlib.Path(storage_dir)
            directory.mkdir(parents=True, exist_ok=True)
            tmp = directory / f".cert_{cert.id}.tmp"
            tmp.write_bytes(content)
            os.replace(tmp, directory / f"cert_{cert.id}.bin")
        except OSError:  # 내용을 못 썼으면 기록도 남기지 않는다(내용 없는 검증서 방지)
            self.session.delete(cert)
            self.session.commit()
            raise
        return cert

    def get_certificate(self, certificate_id):
        return self.session.get(Certificate, certificate_id) if _valid_id(certificate_id) else None

    def read_certificate_content(self, certificate_id, storage_dir):
        if not _valid_id(certificate_id):
            return None
        try:
            return (pathlib.Path(storage_dir) / f"cert_{certificate_id}.bin").read_bytes()
        except OSError:
            return None

    def set_tamper_status(self, certificate_id, status):
        cert = self.get_certificate(certificate_id)
        if cert is None:
            return None
        cert.tamper_status = status
        self.session.commit()
        return cert

    def upsert_personal_info(self, user_id, level, new_pseudonym_id, masked_display_value):
        for _ in range(2):  # 동시에 첫 저장이 겹치면(user_id 유일 제약) 한 번 더 읽어 갱신으로 처리
            row = self.get_personal_info(user_id)
            if row is None:
                row = PersonalInfo(user_id=user_id)
                self.session.add(row)
            row.anonymization_level = level
            row.masked_display_value = masked_display_value
            row.pseudonym_id = (row.pseudonym_id or new_pseudonym_id) if level == "pseudonym" else None
            try:
                self.session.commit()
                return row
            except IntegrityError:
                self.session.rollback()
        raise RuntimeError("personal_info 저장 충돌이 해소되지 않았습니다.")

    def close(self):
        self.session.close()
