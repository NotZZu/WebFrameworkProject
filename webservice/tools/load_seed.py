"""부하 시험용 대량 데이터 적재. 사용: DATABASE_URL=sqlite:///load.db python tools/load_seed.py [사용자 수]
기관 1명(load_inst)과 개인 N명(load_u0001…)을 만들고, 사용자마다 알고리즘 7종 신청(승인·반려·취소 섞음)과
승인된 신청마다 검증서 1건을 넣는다. 모든 계정의 비밀번호는 Load1234. 원본은 한 번만 해시해 재사용한다(적재 속도)."""
import os
import sys

from app import create_app
from app.models import CavpApplication, Certificate, User
from app.services import auth_service
from app.services.cavp_service import ALGORITHMS

PASSWORD = "Load1234"


def main(n_users: int = 430) -> None:
    app = create_app()
    session = app.session_factory()
    pw = auth_service.hash_password(PASSWORD)
    users = [User(username="load_inst", password_hash=pw, user_type="institution", org_code="LOAD-ORG")]
    users += [User(username=f"load_u{i:04d}", password_hash=pw, user_type="individual") for i in range(1, n_users + 1)]
    session.add_all(users)
    session.flush()
    states = ("approved", "approved", "rejected", "cancelled")
    apps = []
    for u in users[1:]:
        for j, algo in enumerate(ALGORITHMS):
            apps.append(CavpApplication(user_id=u.id, algorithm_type=algo, status=states[(u.id + j) % 4]))
    session.add_all(apps)
    session.flush()
    certs = [Certificate(application_id=a.id, cert_type="CAVP" if a.id % 2 else "KCMVP", integrity_hash="a" * 64,
                         tamper_status="suspected" if a.id % 50 == 0 else "normal")
             for a in apps if a.status == "approved"]
    session.add_all(certs)
    session.commit()
    print(f"사용자 {len(users)}, 신청 {len(apps)}, 검증서 {len(certs)}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 430)
