"""API 공통: 요청 DB 세션, JSON 본문 파싱, 로그인 사용자 조회, 오류 핸들러."""
from flask import current_app, g, jsonify, request, session as http_session
from werkzeug.exceptions import HTTPException

from ..errors import AppError, AuthenticationError, ValidationError
from ..services import auth_service


def db():
    if "db" not in g:
        g.db = current_app.session_factory()
    return g.db


def json_body() -> dict:
    try:
        data = request.get_json(silent=True)
    except RecursionError:  # 매우 깊게 중첩된 JSON(DF-05)
        data = None
    if not isinstance(data, dict):
        raise ValidationError("요청 본문은 JSON 객체여야 합니다.")
    return data


def session_user():
    """쿠키의 세션이 서버에 남아 있을 때만 사용자를 돌려준다. 아니면 쿠키를 비우고 None."""
    uid = http_session.get("user_id")
    if uid is None:
        return None
    user = auth_service.user_for_session(db(), uid, http_session.get("sid"))
    if user is None:
        http_session.clear()
    return user


def current_user():
    user = session_user()
    if user is None:
        raise AuthenticationError("로그인이 필요합니다.")
    return user


def user_json(u) -> dict:
    return {"id": u.id, "username": u.username, "user_type": u.user_type}


def error_response(status: int, code: str, message: str):
    return jsonify({"error": {"code": code, "message": message}}), status


def register_error_handlers(app):
    @app.errorhandler(AppError)
    def _app_error(e):
        return error_response(e.http_status, e.code, str(e) or e.code)

    @app.errorhandler(HTTPException)
    def _http_error(e):
        codes = {400: "VALIDATION_ERROR", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 413: "PAYLOAD_TOO_LARGE"}
        if request.path.startswith("/api/"):
            return error_response(e.code, codes.get(e.code, "HTTP_ERROR"), e.description or e.name)
        return e

    @app.teardown_appcontext
    def _close_db(_exc):
        s = g.pop("db", None)
        if s is not None:
            s.close()
