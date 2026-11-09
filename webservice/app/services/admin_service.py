"""관리자 대시보드 요약 (SC-08, FR-06).

get_summary(session, user_id, now=None) → dict
{
  "applications": {"total", "in_progress", "pending_review", "new_last_7d",
                   "by_status": {submitted, reviewing, approved, rejected, cancelled},   # 0건이어도 5개 키 모두
                   "by_algorithm": {AES, SHA-2, SHA-3, HMAC, RSA, ECDSA, DRBG}},          # 0건이어도 7개 키 모두
  "certificates": {"total", "suspected"},
  "recent_applications": [ {id, algorithm_type, owner, status, status_label, submitted_at('YYYY-MM-DD HH:MM')} ],  # 최신순 최대 5건
  "attention": [ {type: 'warning'|'info', message} ],   # 최대 5건, warning 먼저
}
- 기관(institution) 사용자만 조회할 수 있다. 그 밖의 유형은 PermissionDeniedError, 없는 사용자는 NotFoundError.
- 범위는 항상 전체 사용자. 비밀번호·무결성 해시·원본 내용은 포함하지 않는다.
- in_progress = submitted + reviewing, pending_review = submitted (기관이 아직 심사를 시작하지 않은 건).
- attention: ① 위변조 의심 검증서마다 warning '검증서(CV-0007) 위변조 의심 항목이 있습니다.' ② 심사 대기가 있으면 info '심사를 기다리는 신청이 N건 있습니다.'
"""
from datetime import datetime, timedelta

from ..errors import NotFoundError, PermissionDeniedError
from ..models import utcnow
from ..store import as_store
from .cavp_service import ALGORITHMS
from .dashboard_service import STATUS_LABELS


def get_summary(session, user_id: int, now: datetime | None = None) -> dict:
    store = as_store(session)
    now = now or utcnow()
    user = store.get_user(user_id)
    if user is None:
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    if user.user_type != "institution":
        raise PermissionDeniedError("관리자 대시보드는 기관 사용자만 볼 수 있습니다.")

    apps = store.all_applications(None)
    certs = store.list_certificates(None)
    by_status = {k: 0 for k in STATUS_LABELS}
    by_algorithm = {k: 0 for k in ALGORITHMS}
    for a in apps:
        by_status[a.status] = by_status.get(a.status, 0) + 1
        by_algorithm[a.algorithm_type] = by_algorithm.get(a.algorithm_type, 0) + 1
    since = now - timedelta(days=7)

    recent = sorted(apps, key=lambda a: (a.submitted_at, a.id), reverse=True)[:5]
    owners = store.get_users_by_ids({a.user_id for a in recent})
    suspected = sorted((c for c in certs if c.tamper_status == "suspected"), key=lambda c: c.id)
    attention = [{"type": "warning", "message": f"검증서(CV-{c.id:04d}) 위변조 의심 항목이 있습니다."} for c in suspected]
    if by_status["submitted"]:
        attention.append({"type": "info", "message": f"심사를 기다리는 신청이 {by_status['submitted']}건 있습니다."})

    return {
        "applications": {
            "total": len(apps),
            "in_progress": by_status["submitted"] + by_status["reviewing"],
            "pending_review": by_status["submitted"],
            "new_last_7d": sum(1 for a in apps if a.submitted_at >= since),
            "by_status": by_status,
            "by_algorithm": by_algorithm,
        },
        "certificates": {"total": len(certs), "suspected": len(suspected)},
        "recent_applications": [
            {"id": a.id, "algorithm_type": a.algorithm_type,
             "owner": owners[a.user_id].username if a.user_id in owners else None,
             "status": a.status, "status_label": STATUS_LABELS[a.status],
             "submitted_at": a.submitted_at.strftime("%Y-%m-%d %H:%M")}
            for a in recent
        ],
        "attention": attention[:5],
    }
