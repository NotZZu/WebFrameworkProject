"""대시보드 요약 서비스 (SC-02, FR-01·FR-03·FR-04). 계약만 정의 — 구현은 Green 단계.

get_summary(session, user_id, now=None) → dict
{
  "scope": "own" | "all",                       # institution 사용자는 'all'(전체 신청·검증서), 그 외 'own'
  "user": {"username", "user_type"},            # 비밀번호/해시 등 민감 필드는 포함하지 않는다
  "applications": {"total", "in_progress",      # in_progress = submitted + reviewing
                   "by_status": {submitted, reviewing, approved, rejected},   # 0건이어도 4개 키 모두
                   "new_last_7d"},               # submitted_at >= now - 7일 (경계 포함)
  "certificates": {"total", "suspected"},       # suspected = tamper_status 'suspected'
  "privacy": {"processed": bool, "level": "pseudonym"|"anonymous"|None},   # 항상 본인 기준
  "recent_applications": [ {id, algorithm_type, status, status_label, submitted_at('YYYY-MM-DD')} ],  # 최신순 최대 3건
  "notifications": [ {type: 'warning'|'info', message} ],                   # 최대 5건
}
status_label: submitted→'접수 대기', reviewing→'시험 진행중', approved→'시험 완료', rejected→'반려'
알림 규칙: ① 위변조 의심 검증서마다 warning '검증서(CV-0007) 위변조 의심 항목이 있습니다.'(번호는 4자리 0 채움) 최우선
          ② 그 외 info — reviewing '{알고리즘} 시험이 심사 중입니다.', approved '{알고리즘} 시험이 승인되었습니다.',
            rejected '{알고리즘} 시험이 반려되었습니다.' (submitted 는 알림 없음), updated_at 최신순
없는 사용자: NotFoundError
"""
from datetime import datetime, timedelta

from sqlalchemy import select

from ..errors import NotFoundError
from ..models import CavpApplication, Certificate, PersonalInfo, User, utcnow

STATUS_LABELS = {"submitted": "접수 대기", "reviewing": "시험 진행중", "approved": "시험 완료", "rejected": "반려"}
_INFO_MESSAGES = {
    "reviewing": "{algo} 시험이 심사 중입니다.",
    "approved": "{algo} 시험이 승인되었습니다.",
    "rejected": "{algo} 시험이 반려되었습니다.",
}


def get_summary(session, user_id: int, now: datetime | None = None) -> dict:
    now = now or utcnow()
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("사용자를 찾을 수 없습니다.")

    scope = "all" if user.user_type == "institution" else "own"
    app_q = select(CavpApplication)
    cert_q = select(Certificate)
    if scope == "own":
        app_q = app_q.where(CavpApplication.user_id == user.id)
        cert_q = cert_q.join(CavpApplication, Certificate.application_id == CavpApplication.id) \
            .where(CavpApplication.user_id == user.id)
    apps = list(session.scalars(app_q))
    certs = list(session.scalars(cert_q))

    by_status = {k: 0 for k in STATUS_LABELS}
    for a in apps:
        by_status[a.status] = by_status.get(a.status, 0) + 1
    since = now - timedelta(days=7)

    recent = sorted(apps, key=lambda a: (a.submitted_at, a.id), reverse=True)[:3]
    suspected = sorted((c for c in certs if c.tamper_status == "suspected"), key=lambda c: c.id)
    notifications = [
        {"type": "warning", "message": f"검증서(CV-{c.id:04d}) 위변조 의심 항목이 있습니다."} for c in suspected
    ]
    for a in sorted(apps, key=lambda a: (a.updated_at, a.id), reverse=True):
        if a.status in _INFO_MESSAGES:
            notifications.append({"type": "info", "message": _INFO_MESSAGES[a.status].format(algo=a.algorithm_type)})

    info = session.scalar(select(PersonalInfo).where(PersonalInfo.user_id == user.id))
    return {
        "scope": scope,
        "user": {"username": user.username, "user_type": user.user_type},
        "applications": {
            "total": len(apps),
            "in_progress": by_status["submitted"] + by_status["reviewing"],
            "by_status": by_status,
            "new_last_7d": sum(1 for a in apps if a.submitted_at >= since),
        },
        "certificates": {"total": len(certs), "suspected": len(suspected)},
        "privacy": {"processed": info is not None, "level": info.anonymization_level if info else None},
        "recent_applications": [
            {"id": a.id, "algorithm_type": a.algorithm_type, "status": a.status,
             "status_label": STATUS_LABELS[a.status], "submitted_at": a.submitted_at.strftime("%Y-%m-%d")}
            for a in recent
        ],
        "notifications": notifications[:5],
    }
