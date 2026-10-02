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
from datetime import datetime

STATUS_LABELS = {"submitted": "접수 대기", "reviewing": "시험 진행중", "approved": "시험 완료", "rejected": "반려"}


def get_summary(session, user_id: int, now: datetime | None = None) -> dict:
    raise NotImplementedError
