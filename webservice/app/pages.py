"""화면(HTML) 라우트: SC-01 로그인/회원가입, SC-02 대시보드(자리표시)."""
from flask import Blueprint, redirect, render_template, session as http_session, url_for

from .api.helpers import db
from .errors import AppError
from .services import auth_service

bp = Blueprint("pages", __name__)


@bp.get("/")
def login_page():
    if http_session.get("user_id"):
        return redirect(url_for("pages.dashboard"))
    return render_template("login.html")


@bp.get("/dashboard")
def dashboard():
    uid = http_session.get("user_id")
    if not uid:
        return redirect(url_for("pages.login_page"))
    try:
        user = auth_service.get_user(db(), uid)
    except AppError:
        http_session.clear()
        return redirect(url_for("pages.login_page"))
    return render_template("dashboard_placeholder.html", user=user)
