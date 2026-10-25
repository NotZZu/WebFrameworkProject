"""CAVP 시험 신청 API (FR-03): /api/cavp/applications"""
from flask import Blueprint, jsonify, request

from ..errors import ValidationError
from ..services import cavp_service
from ..services.dashboard_service import STATUS_LABELS
from .helpers import current_user, db, json_body

bp = Blueprint("cavp_api", __name__, url_prefix="/api/cavp")


def application_json(a) -> dict:
    return {"id": a.id, "algorithm_type": a.algorithm_type, "status": a.status,
            "status_label": STATUS_LABELS[a.status],
            "submitted_at": a.submitted_at.strftime("%Y-%m-%d %H:%M"),
            "updated_at": a.updated_at.strftime("%Y-%m-%d %H:%M")}


def _int_param(name, default):
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValidationError(f"{name} 값이 올바르지 않습니다.")


@bp.get("/algorithms")
def algorithms():
    current_user()
    return jsonify({"algorithms": list(cavp_service.ALGORITHMS)})


@bp.post("/applications")
def create():
    user = current_user()
    app = cavp_service.create_application(db(), user.id, json_body().get("algorithm_type"))
    return jsonify(application_json(app)), 201


@bp.get("/applications")
def list_():
    user = current_user()
    res = cavp_service.list_applications(db(), user.id, status=request.args.get("status"),
                                         page=_int_param("page", 1), per_page=_int_param("per_page", 10))
    return jsonify({"items": [application_json(a) for a in res["items"]], "total": res["total"],
                    "page": res["page"], "per_page": res["per_page"]})
