"""검증서 API (FR-04·FR-05): 발급, 이력 조회(SC-06), 위변조 검증(SC-07).
응답에는 저장 경로·해시 원문·검증서 내용을 싣지 않는다."""
from flask import Blueprint, current_app, jsonify, request

from ..errors import ValidationError
from ..services import certificate_service
from .helpers import current_user, db, json_body

bp = Blueprint("certificates_api", __name__, url_prefix="/api")
TAMPER_LABELS = {"normal": "정상", "suspected": "위변조 의심"}


def certificate_json(c, app=None, owner=None) -> dict:
    return {"id": c.id, "application_id": c.application_id, "algorithm_type": app.algorithm_type if app else None,
            "owner": owner, "cert_type": c.cert_type, "issued_at": c.issued_at.strftime("%Y-%m-%d %H:%M"),
            "tamper_status": c.tamper_status, "tamper_label": TAMPER_LABELS[c.tamper_status]}


def _int_param(name, default):
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValidationError(f"{name} 값이 올바르지 않습니다.")


def _decorate(certs, with_owner):
    store = db()
    apps = {c.application_id: store.get_application(c.application_id) for c in certs}
    users = store.get_users_by_ids({a.user_id for a in apps.values() if a}) if with_owner else {}
    return [certificate_json(c, apps.get(c.application_id),
                             users[apps[c.application_id].user_id].username if with_owner and apps.get(c.application_id)
                             and apps[c.application_id].user_id in users else None) for c in certs]


@bp.post("/cavp/applications/<int:app_id>/certificate")
def issue(app_id):
    user = current_user()
    body = json_body()
    content = body.get("content")
    if not isinstance(content, str):
        raise ValidationError("검증서 내용을 입력해 주세요.")
    cert = certificate_service.issue_certificate(db(), user.id, app_id, body.get("cert_type"), content.encode("utf-8"),
                                                 current_app.config["CERT_STORAGE_DIR"])
    return jsonify(_decorate([cert], user.user_type == "institution")[0]), 201


@bp.get("/certificates")
def list_():
    user = current_user()
    all_scope = user.user_type == "institution"  # 기관은 신청과 마찬가지로 전체 범위
    res = certificate_service.list_certificates(db(), user.id, page=_int_param("page", 1),
                                                per_page=_int_param("per_page", 10), include_all=all_scope)
    return jsonify({"items": _decorate(res["items"], all_scope), "total": res["total"], "page": res["page"],
                    "per_page": res["per_page"], "scope": "all" if all_scope else "own"})


@bp.get("/certificates/<int:certificate_id>")
def detail(certificate_id):
    user = current_user()
    cert = certificate_service.get_certificate(db(), user.id, certificate_id)
    return jsonify(_decorate([cert], user.user_type == "institution")[0])


@bp.get("/certificates/<int:certificate_id>/verify")
def verify(certificate_id):
    user = current_user()
    certificate_service.get_certificate(db(), user.id, certificate_id)  # 조회 권한이 있는 사람만 검증할 수 있다
    cert = certificate_service.verify_integrity(db(), certificate_id, current_app.config["CERT_STORAGE_DIR"])
    return jsonify(_decorate([cert], user.user_type == "institution")[0])
