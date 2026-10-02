"""SC-02 대시보드 API."""
from flask import Blueprint, jsonify

from ..services import dashboard_service
from .helpers import current_user, db

bp = Blueprint("dashboard_api", __name__, url_prefix="/api/dashboard")


@bp.get("")
def summary():
    user = current_user()
    return jsonify(dashboard_service.get_summary(db(), user.id))
