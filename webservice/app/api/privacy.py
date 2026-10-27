"""SC-03 가명·익명정보 처리 API (FR-02). 원본 이름·생년월일은 요청에서 읽어 변환만 하고 저장·응답하지 않는다."""
import re
from datetime import date

from flask import Blueprint, jsonify

from ..errors import ValidationError
from ..services import privacy_service
from .helpers import current_user, db, json_body

bp = Blueprint("privacy_api", __name__, url_prefix="/api/privacy")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _parse_birthdate(raw) -> date:
    if not isinstance(raw, str) or not _ISO_DATE.fullmatch(raw):  # 'YYYY-MM-DD' 만 허용(주차·숫자 형식 등 거부)
        raise ValidationError("생년월일은 YYYY-MM-DD 형식이어야 합니다.")
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValidationError("생년월일이 올바르지 않습니다.")


def _json(info) -> dict:
    return {"level": info.anonymization_level, "pseudonym_id": info.pseudonym_id, "display": info.masked_display_value}


@bp.post("/process")
def process():
    user = current_user()
    body = json_body()  # user_id·pseudonym_id 같은 다른 필드는 읽지 않는다(항상 로그인한 본인 것만 처리)
    info = privacy_service.process_and_store(db(), user.id, body.get("mode"), body.get("name"),
                                             _parse_birthdate(body.get("birthdate")))
    return jsonify(_json(info))


@bp.get("/me")
def mine():
    user = current_user()
    return jsonify(_json(privacy_service.get_privacy_info(db(), user.id)))
