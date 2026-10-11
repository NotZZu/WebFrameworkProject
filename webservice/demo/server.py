"""시험 시연 서버 — 서비스와 분리된 별도 앱. 버튼으로 실제 시험을 서버에서 실행하고 결과를 실시간 제공한다.

실행: gunicorn -b 0.0.0.0:8000 -w 1 --threads 8 demo.server:app
환경변수: SERVICE_URL(서비스 주소 표시용), PAGES_URL, REPO_URL
"""
import json
import os
import pathlib
import subprocess
import sys
import threading

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

from .runner import ROOT, SUITES, Runner

app = Flask(__name__, template_folder="templates")
runner = Runner()
_cases = {"data": None}
_cases_lock = threading.Lock()

REPO_URL = os.environ.get("REPO_URL", "https://github.com/NotZZu/WebFrameworkProject")
PAGES_URL = os.environ.get("PAGES_URL", "https://notzzu.github.io/WebFrameworkProject/")
SERVICE_URL = os.environ.get("SERVICE_URL", "")


def load_cases() -> list[dict]:
    """@case 레지스트리(전체 케이스 목록)를 한 번만 내보내 캐시한다."""
    with _cases_lock:
        if _cases["data"] is None:
            out = pathlib.Path(os.environ.get("DEMO_RUN_DIR", "/tmp/demo-runs")) / "cases.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run([sys.executable, "scripts/export_cases.py", str(out)], cwd=ROOT, check=True,
                               capture_output=True, timeout=120)
                _cases["data"] = json.loads(out.read_text(encoding="utf-8"))
            except Exception:
                return []          # 실패 결과는 캐시하지 않는다(다음 요청에서 다시 시도)
        return _cases["data"]


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.get("/")
def index():
    return render_template("index.html", suites=SUITES, repo_url=REPO_URL, pages_url=PAGES_URL, service_url=SERVICE_URL)


@app.get("/api/cases")
def cases():
    return jsonify([{k: c[k] for k in ("id", "req", "title", "expect", "kind", "func", "module", "runs")} for c in load_cases()])


@app.post("/api/run")
def start_run():
    body = request.get_json(silent=True) or {}
    ids = body.get("cases")
    if ids is not None:
        by_id = {c["id"]: c for c in load_cases()}
        if not isinstance(ids, list) or not ids or len(ids) > 500 or any(not isinstance(i, str) or i not in by_id for i in ids):
            return jsonify(error="선택한 시험 번호가 올바르지 않습니다."), 400
        ids = sorted(set(ids))
        paths = sorted({by_id[i]["module"].replace(".", "/") + ".py" for i in ids})
        rid, busy = runner.start("picked", cases=ids, case_paths=paths)
        if rid is None:
            return jsonify(error="이미 시험이 실행 중입니다. 끝난 뒤 다시 시도하세요.", running=busy), 409
        return jsonify(run_id=rid), 202
    suite = body.get("suite", "all")
    if suite not in SUITES:
        return jsonify(error="알 수 없는 시험 묶음입니다."), 400
    rid, busy = runner.start(suite)
    if rid is None:
        return jsonify(error="이미 시험이 실행 중입니다. 끝난 뒤 다시 시도하세요.", running=busy), 409
    return jsonify(run_id=rid), 202


@app.get("/api/run/<rid>")
def run_status(rid):
    snap = runner.snapshot(rid, int(request.args.get("since", 0)))
    if snap is None:
        abort(404)
    return jsonify(snap)


@app.get("/api/run/<rid>/shots/<name>")
def shot(rid, name):
    r = runner.runs.get(rid)
    if not r or "/" in name or not name.endswith(".png"):
        abort(404)
    return send_from_directory(r["dir"] / "shots", name)
