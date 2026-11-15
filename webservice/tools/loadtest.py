"""간단한 부하 측정(표준 라이브러리만 사용). 사용: python tools/loadtest.py http://127.0.0.1:5056 [동시 수] [시나리오당 요청 수]
load_seed.py 로 만든 계정(load_inst, load_u0001…)으로 로그인해 주요 API 를 동시에 호출하고
지연(중앙값·95%·최대), 초당 처리량, 오류 건수를 표로 출력한다. 읽기와 쓰기를 따로 잰다."""
import http.client
import json
import os
import random
import statistics
import sys
import threading
import time
from urllib.parse import urlparse


# 계정 설정(환경변수로 바꾼다). 기본값은 load_seed.py 가 만든 로컬 시험 계정.
INST = os.environ.get("LOAD_INST", "load_inst")
PREFIX = os.environ.get("LOAD_USER_PREFIX", "load_u")
NUSERS = int(os.environ.get("LOAD_NUSERS", "400"))
PASSWORD = os.environ.get("LOAD_PASSWORD", "Load1234")


class Client:
    def __init__(self, base):
        u = urlparse(base)
        self.tls = u.scheme == "https"
        self.host, self.port = u.hostname, u.port or (443 if self.tls else 80)
        self.cookie = ""
        self.conn = self._new_conn()

    def _new_conn(self):
        cls = http.client.HTTPSConnection if self.tls else http.client.HTTPConnection
        return cls(self.host, self.port, timeout=60)

    def call(self, method, path, body=None):
        headers = {"Cookie": self.cookie, "Content-Type": "application/json"} if self.cookie else {"Content-Type": "application/json"}
        data = json.dumps(body) if body is not None else None
        for attempt in (1, 2):  # 서버가 쉬던 연결을 닫았을 수 있어 한 번은 새 연결로 다시 보낸다(측정기 쪽 오류 제거)
            try:
                self.conn.request(method, path, body=data, headers=headers)
                r = self.conn.getresponse()
                raw = r.read()
                break
            except (http.client.HTTPException, OSError):
                self.conn.close()
                self.conn = self._new_conn()
                if attempt == 2:
                    return 0, b""
        sc = r.getheader("Set-Cookie")
        if sc:
            self.cookie = sc.split(";", 1)[0]
        return r.status, raw

    def login(self, username, password=None):
        password = password or PASSWORD
        return self.call("POST", "/api/auth/login", {"username": username, "password": password})[0]


def run(name, workers, total, make_client, action, ok=(200,)):
    clients = [make_client(i) for i in range(workers)]
    lat, bad, lock = [], {}, threading.Lock()
    per = max(1, total // workers)

    def work(c):
        for _ in range(per):
            t = time.perf_counter()
            status = action(c)
            d = time.perf_counter() - t
            with lock:
                lat.append(d)
                if status not in ok:
                    bad[status] = bad.get(status, 0) + 1
    t0 = time.perf_counter()
    ths = [threading.Thread(target=work, args=(c,)) for c in clients]
    [t.start() for t in ths]
    [t.join() for t in ths]
    wall = time.perf_counter() - t0
    lat.sort()
    n = len(lat)
    return {"name": name, "n": n, "rps": n / wall, "p50": statistics.median(lat) * 1000,
            "p95": lat[int(n * 0.95) - 1] * 1000, "max": lat[-1] * 1000, "bad": bad}


def main():
    base = sys.argv[1]
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 16
    total = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    inst_clients = {}

    def inst(i):
        c = Client(base)
        assert c.login(INST) == 200, f"{INST} 로그인 실패 (시딩을 먼저 실행)"
        return c
    rows = [
        run("대시보드(기관)", workers, total, inst, lambda c: c.call("GET", "/api/dashboard")[0]),
        run("관리자 요약", workers, total, inst, lambda c: c.call("GET", "/api/admin/summary")[0]),
        run("신청 목록 1쪽", workers, total, inst, lambda c: c.call("GET", "/api/cavp/applications?page=1")[0]),
        run("검증서 목록", workers, total, inst, lambda c: c.call("GET", "/api/certificates")[0]),
    ]

    def user(i):
        c = Client(base)
        assert c.login(f"{PREFIX}{(i % NUSERS) + 1:04d}") == 200
        c.uid = (i % NUSERS) + 1
        return c
    rows.append(run("개인 대시보드", workers, total, user, lambda c: c.call("GET", "/api/dashboard")[0]))
    rows.append(run("신청 생성(쓰기)", workers, total, user,
                    lambda c: c.call("POST", "/api/cavp/applications", {"algorithm_type": random.choice(["AES", "SHA-2", "SHA-3", "HMAC", "RSA", "ECDSA", "DRBG"])})[0],
                    ok=(201, 409)))
    nlogin = max(workers, 16)
    rows.append(run("로그인(bcrypt)", min(workers, 8), nlogin, lambda i: Client(base),
                    lambda c: c.login(f"{PREFIX}{random.randint(1, NUSERS):04d}")))
    print(f"동시 {workers}, 시나리오당 약 {total}건")
    print(f"{'시나리오':<14}{'건수':>6}{'초당':>8}{'중앙값ms':>10}{'95%ms':>9}{'최대ms':>9}  오류")
    for r in rows:
        print(f"{r['name']:<14}{r['n']:>6}{r['rps']:>8.1f}{r['p50']:>10.0f}{r['p95']:>9.0f}{r['max']:>9.0f}  {r['bad'] or '-'}")


if __name__ == "__main__":
    main()
