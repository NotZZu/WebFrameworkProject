"""인증 API (FR-01): /api/auth/*"""
from flask import Blueprint, jsonify, session as http_session

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
    user = auth_service.login(db(), b.get("username"), b.get("password"))
    http_session.clear()
    http_session["user_id"] = user.id
    return jsonify(user_json(user)), 200


@bp.post("/logout")
def logout():
    http_session.clear()
    return "", 204


@bp.get("/me")
def me():
    return jsonify(user_json(current_user()))
