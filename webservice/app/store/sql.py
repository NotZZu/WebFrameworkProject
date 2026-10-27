"""SQLAlchemy 구현. 기존 서비스 코드의 질의를 그대로 옮겼다."""
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from ..errors import DuplicateApplicationError, DuplicateUsernameError
from ..models import ActiveSession, CavpApplication, Certificate, PersonalInfo, User, utcnow
from .base import Store


class SqlStore(Store):
    def __init__(self, session):
        self.session = session

    # ---- 사용자 ----
    def get_user(self, user_id):
        return self.session.get(User, user_id)

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
        return self.session.get(CavpApplication, application_id)

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

    def close(self):
        self.session.close()
