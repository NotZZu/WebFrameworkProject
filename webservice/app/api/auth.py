"""인증 API (FR-01): /api/auth/*"""
from flask import Blueprint, current_app, jsonify, session as http_session

from ..errors import AuthenticationError, TooManyAttemptsError
from ..services import auth_service
from .helpers import current_user, db, json_body, user_json

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/signup")
def signup():
    b = json_body()
    user = auth_service.signup(db(), b.get("username"), b.get("password"),
                               b.get("user_type"), b.get("org_code"))
    return jsonify(user_json(user)), 201


@bp.post("/login")
def login():
    b = json_body()
    throttle, name = current_app.login_throttle, b.get("username")
    if throttle.is_blocked(name):
        raise TooManyAttemptsError("로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.")
    try:
        user = auth_service.login(db(), name, b.get("password"))
    except AuthenticationError:
        throttle.record_failure(name)
        raise
    throttle.reset(name)
    http_session.clear()
    http_session["user_id"] = user.id
    http_session["sid"] = auth_service.start_session(db(), user.id)
    return jsonify(user_json(user)), 200


@bp.post("/logout")
def logout():
    auth_service.end_session(db(), http_session.get("sid"))
    http_session.clear()
    return "", 204


@bp.get("/me")
def me():
    return jsonify(user_json(current_user()))
