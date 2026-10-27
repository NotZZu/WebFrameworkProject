"""저장소 인터페이스. 구현체는 아래 메서드를 모두 제공해야 한다."""


class Store:
    # ---- 사용자 ----
    def get_user(self, user_id):
        """id 로 사용자 조회. 없으면 None."""
        raise NotImplementedError

    def get_user_by_username(self, username):
        """아이디(대소문자 구분)로 조회. 없으면 None."""
        raise NotImplementedError

    def add_user(self, username, password_hash, user_type, org_code):
        """사용자 저장. 같은 아이디가 이미 있으면(동시 요청 포함) DuplicateUsernameError."""
        raise NotImplementedError

    def get_users_by_ids(self, ids) -> dict:
        """{id: User}. 없는 id 는 빠진다."""
        raise NotImplementedError

    # ---- 로그인 세션 ----
    def add_session(self, sid, user_id):
        raise NotImplementedError

    def get_session(self, sid):
        """없으면 None."""
        raise NotImplementedError

    def delete_session(self, sid):
        """없어도 오류 없이 끝난다."""
        raise NotImplementedError

    # ---- 시험 신청 ----
    def create_application(self, user_id, algorithm_type):
        """상태 submitted 로 저장. 같은 사용자·같은 알고리즘의 진행 중(submitted/reviewing) 신청이
        이미 있으면(동시 요청 포함) DuplicateApplicationError. 검사와 저장은 쪼갤 수 없는 한 동작이어야 한다(DF-13)."""
        raise NotImplementedError

    def get_application(self, application_id):
        """없으면 None. 다른 요청이 방금 바꾼 값이 보여야 한다."""
        raise NotImplementedError

    def change_application_status(self, application_id, expected_status, new_status) -> bool:
        """현재 상태가 expected_status 일 때만 new_status 로 바꾸고 updated_at 을 갱신한다.
        바꿨으면 True, 조건이 맞지 않아 바꾸지 못했으면 False. 쪼갤 수 없는 한 동작이어야 한다(DF-14)."""
        raise NotImplementedError

    def list_applications(self, user_id, status, page, per_page):
        """(items, total). user_id 가 None 이면 전체. submitted_at 내림차순, id 내림차순."""
        raise NotImplementedError

    def all_applications(self, user_id):
        """조건에 맞는 신청 전체 목록(대시보드 집계용). user_id 가 None 이면 전체."""
        raise NotImplementedError

    # ---- 검증서·가명정보 (대시보드 집계용) ----
    def list_certificates(self, user_id):
        """user_id 가 None 이면 전체, 아니면 그 사용자의 신청에 속한 검증서."""
        raise NotImplementedError

    def get_personal_info(self, user_id):
        """없으면 None."""
        raise NotImplementedError

    def close(self):
        pass


def as_store(obj) -> "Store":
    """Store 는 그대로, SQLAlchemy 세션이면 SqlStore 로 감싼다(기존 시험·호출부 호환)."""
    if isinstance(obj, Store):
        return obj
    from .sql import SqlStore
    return SqlStore(obj)
