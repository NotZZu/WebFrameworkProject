"""초기 데이터 적재 (시스템설계서 v1.1 5.3절 / D12). 계약만 정의.

seed(session) → {'users': n, 'personal_info': n, 'applications': n, 'certificates': n}
- 사용자 3종(demo_individual, demo_company, demo_institution), 공통 비밀번호 'Demo1234'(bcrypt 저장).
- 신청 4건 이상(4개 상태 모두 포함), 검증서 3건(그중 1건 tamper_status='suspected').
- 멱등: 두 번 실행해도 건수가 늘지 않는다.
"""


def seed(session) -> dict:
    raise NotImplementedError
