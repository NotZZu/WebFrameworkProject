"""화면(HTML) 라우트: SC-01 로그인/회원가입, SC-02 대시보드, SC-03 가명·익명정보 처리, SC-04/05 CAVP, SC-06 검증서 이력, SC-07 위변조 탐지."""
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


@bp.get("/privacy")
def privacy():
    user = session_user()
    if user is None:
        return redirect(url_for("pages.login_page"))
    return render_template("privacy.html", user=user)


@bp.get("/certificates")
def certificates():
    user = session_user()
    if user is None:
        return redirect(url_for("pages.login_page"))
    return render_template("certificates.html", user=user, page="history")


@bp.get("/tamper")
def tamper():
    user = session_user()
    if user is None:
        return redirect(url_for("pages.login_page"))
    return render_template("certificates.html", user=user, page="tamper")


@bp.get("/cavp/apply")
def cavp_apply():
    user = session_user()
    if user is None:
        return redirect(url_for("pages.login_page"))
    return render_template("cavp_apply.html", user=user)


@bp.get("/cavp/status")
def cavp_status():
    user = session_user()
    if user is None:
        return redirect(url_for("pages.login_page"))
    return render_template("cavp_status.html", user=user)


@bp.get("/healthz")
def healthz():
    """배포 환경 상태 확인(로드밸런서·모니터링용). 인증 불필요, DB 접근 없음."""
    return jsonify(status="ok")
