"""배포된 서비스(HTTPS)에 소량의 시험 데이터를 API 로 넣는다. 사용:
  LOAD_PASSWORD=<임의 비밀번호> python3 tools/aws_seed.py https://<도메인> [사용자 수=30]
기관 1명(aws_inst)과 개인 N명(aws_u0001…)을 가입시키고, 사용자마다 알고리즘 7종을 신청한 뒤 절반을 승인·검증서 발급한다.
DynamoDB 프로비저닝 쓰기 용량(10 WCU)을 넘지 않게 호출 사이를 띄우고, 제한(429/5xx)이 보이면 더 오래 쉰다."""
import os
import sys
import time

from loadtest import Client

ALGOS = ["AES", "SHA-2", "SHA-3", "HMAC", "RSA", "ECDSA", "DRBG"]
PAUSE = float(os.environ.get("SEED_PAUSE", "0.5"))


def call(c, method, path, body=None, ok=(200, 201, 409)):
    for attempt in range(6):
        st, raw = c.call(method, path, body)
        if st in ok:
            return st, raw
        time.sleep(2 * (attempt + 1) if st in (0, 429, 500, 502, 503, 504) else 0)
        if st not in (0, 429, 500, 502, 503, 504):
            break
    raise SystemExit(f"실패: {method} {path} → {st} {raw[:120]!r}")


def main(base, n):
    pw = os.environ["LOAD_PASSWORD"]
    inst = Client(base)
    call(inst, "POST", "/api/auth/signup", {"username": "aws_inst", "password": pw, "user_type": "institution", "org_code": "AWS-LOAD"})
    call(inst, "POST", "/api/auth/login", {"username": "aws_inst", "password": pw})
    done = 0
    for i in range(1, n + 1):
        name = f"aws_u{i:04d}"
        c = Client(base)
        call(c, "POST", "/api/auth/signup", {"username": name, "password": pw, "user_type": "individual"})
        call(c, "POST", "/api/auth/login", {"username": name, "password": pw})
        for j, algo in enumerate(ALGOS):
            st, raw = call(c, "POST", "/api/cavp/applications", {"algorithm_type": algo})
            time.sleep(PAUSE)
            if st != 201 or (i + j) % 2:
                continue
            import json
            app_id = json.loads(raw)["id"]
            call(inst, "PATCH", f"/api/cavp/applications/{app_id}/status", {"status": "reviewing"})
            call(inst, "PATCH", f"/api/cavp/applications/{app_id}/status", {"status": "approved"})
            call(inst, "POST", f"/api/cavp/applications/{app_id}/certificate", {"cert_type": "CAVP", "content": f"load certificate {app_id}"})
            time.sleep(PAUSE)
        done += 1
        print(f"사용자 {done}/{n} 완료", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 30)
