"""SC-08 관리자 대시보드 API: /api/admin/summary (기관 전용)"""
from flask import Blueprint, jsonify

from ..services import admin_service
from .helpers import current_user, db

bp = Blueprint("admin_api", __name__, url_prefix="/api/admin")


@bp.get("/summary")
def summary():
    user = current_user()
    return jsonify(admin_service.get_summary(db(), user.id))
