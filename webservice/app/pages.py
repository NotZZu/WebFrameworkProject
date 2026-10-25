"""화면(HTML) 라우트: SC-01 로그인/회원가입, SC-02 대시보드."""
from flask import Blueprint, jsonify, redirect, render_template, url_for

from .api.helpers import session_user

bp = Blueprint("pages", __name__)


@bp.get("/")
def login_page():
    if session_user() is not None:
        return redirect(url_for("pages.dashboard"))
    return render_template("login.html")


@bp.get("/dashboard")
def dashboard():
    user = session_user()
    if user is None:
        return redirect(url_for("pages.login_page"))
    return render_template("dashboard.html", user=user)


@bp.get("/cavp/apply")
def cavp_apply():
    user = session_user()
    if user is None:
        return redirect(url_for("pages.login_page"))
    return render_template("cavp_apply.html", user=user)


@bp.get("/healthz")
def healthz():
    """배포 환경 상태 확인(로드밸런서·모니터링용). 인증 불필요, DB 접근 없음."""
    return jsonify(status="ok")
