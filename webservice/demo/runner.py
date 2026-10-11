"""시험 실행 관리: 한 번에 한 건만 실행, 결과 이벤트 파일을 읽어 상태를 제공한다."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent          # webservice/
RUN_DIR = pathlib.Path(os.environ.get("DEMO_RUN_DIR", "/tmp/demo-runs"))
TIMEOUT = int(os.environ.get("DEMO_TIMEOUT", "420"))
KEEP = 5

SUITES = {
    "all": ("전체 시험", ["tests"]),
    "unit": ("단위 시험", ["tests/unit"]),
    "integration": ("통합 시험", ["tests/integration"]),
    "e2e": ("브라우저 E2E", ["tests/e2e"]),
}


def build_command(suite: str) -> list[str]:
    if suite not in SUITES:
        raise ValueError(f"알 수 없는 시험 묶음: {suite}")
    return [sys.executable, "-m", "pytest", "-p", "demo.live_plugin", "-p", "no:cacheprovider", "-q", *SUITES[suite][1]]


class Runner:
    def __init__(self, run_dir=RUN_DIR, command_builder=build_command):
        self.run_dir = pathlib.Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.command_builder = command_builder
        self._lock = threading.Lock()
        self.runs: dict[str, dict] = {}
        self.current: str | None = None

    # ---- 시작
    def start(self, suite: str) -> tuple[str | None, str | None]:
        """→ (run_id, None) 성공 / (None, 실행 중 run_id) 이미 실행 중."""
        cmd = self.command_builder(suite)
        with self._lock:
            if self.current and self.runs[self.current]["status"] == "running":
                return None, self.current
            rid = time.strftime("%H%M%S-") + uuid.uuid4().hex[:6]
            d = self.run_dir / rid
            (d / "shots").mkdir(parents=True)
            self.runs[rid] = dict(id=rid, suite=suite, label=SUITES.get(suite, (suite,))[0], status="running",
                                  started=time.time(), finished=None, dir=d, exit=None)
            self.current = rid
            self._prune()
        threading.Thread(target=self._run, args=(rid, cmd), daemon=True).start()
        return rid, None

    def _run(self, rid, cmd):
        r = self.runs[rid]; d = r["dir"]
        env = {**os.environ, "DEMO_EVENTS": str(d / "events.jsonl"), "E2E_ARTIFACT_DIR": str(d / "shots"),
               "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1"}
        try:
            with open(d / "output.log", "w", encoding="utf-8") as log:
                p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                try:
                    r["exit"] = p.wait(timeout=TIMEOUT)
                except subprocess.TimeoutExpired:
                    p.kill(); r["exit"] = -9
                    log.write("\n[시연 서버] 제한 시간 초과로 중단되었습니다.\n")
            r["status"] = "done" if r["exit"] in (0, 1) else "error"
        except Exception as e:  # pragma: no cover
            r["status"] = "error"; r["exit"] = -1
            (d / "output.log").write_text(f"실행 오류: {e}", encoding="utf-8")
        r["finished"] = time.time()

    def _prune(self):
        for rid in sorted(self.runs, key=lambda k: self.runs[k]["started"])[:-KEEP]:
            if self.runs[rid]["status"] != "running":
                shutil.rmtree(self.runs[rid]["dir"], ignore_errors=True)
                del self.runs[rid]

    # ---- 조회
    def snapshot(self, rid: str, since: int = 0) -> dict | None:
        r = self.runs.get(rid)
        if not r:
            return None
        d = r["dir"]; results, total, ev_finished = [], None, False
        ev = d / "events.jsonl"
        if ev.exists():
            for line in ev.read_text(encoding="utf-8").splitlines():
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e["type"] == "collected":
                    total = e["total"]
                elif e["type"] == "result":
                    results.append(e)
                elif e["type"] == "finished":
                    ev_finished = True
        counts = {k: sum(1 for x in results if x["status"] == k) for k in ("pass", "red", "fail", "skip")}
        log = (d / "output.log").read_text(encoding="utf-8", errors="replace")[-3000:] if (d / "output.log").exists() else ""
        shots = sorted(p.name for p in (d / "shots").glob("*.png"))
        return dict(id=rid, suite=r["suite"], label=r["label"], status=r["status"], total=total, counts=counts,
                    done=len(results), results=results[since:], next=len(results), shots=shots, log=log,
                    exit=r["exit"], started=r["started"], finished=r["finished"], finished_events=ev_finished,
                    elapsed=round((r["finished"] or time.time()) - r["started"], 1))
