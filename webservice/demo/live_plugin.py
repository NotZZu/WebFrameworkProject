"""pytest 플러그인: 시험 결과를 케이스 단위로 JSON Lines 파일에 실시간 기록 (시험 시연 페이지용).

사용: DEMO_EVENTS=<경로> python -m pytest -p demo.live_plugin ...
이벤트: {"type":"collected","total":N} / {"type":"result", ...} / {"type":"finished"}
"""
import json
import os
import time

import pytest

_OUT = os.environ.get("DEMO_EVENTS")


def _emit(obj):
    if not _OUT:
        return
    with open(_OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def pytest_collection_finish(session):
    _emit({"type": "collected", "total": len(session.items)})


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call" and not (rep.when == "setup" and (rep.failed or rep.skipped)):
        return
    if hasattr(rep, "wasxfail"):
        status = "red" if rep.skipped else "pass"
    elif rep.failed:
        status = "fail"
    elif rep.skipped:
        status = "skip"
    else:
        status = "pass"
    # strict xfail 이 예기치 않게 통과하면 report.failed + 'XPASS(strict)' → fail
    marker = item.get_closest_marker("case")
    case_id = marker.args[0] if marker and marker.args else None
    msg = ""
    if status == "fail" and call.excinfo is not None:
        msg = str(call.excinfo.value).strip().splitlines()[0][:200] if str(call.excinfo.value).strip() else call.excinfo.typename
    elif status == "fail":
        msg = (str(rep.longrepr).strip().splitlines() or [""])[-1][:200]
    _emit({"type": "result", "nodeid": item.nodeid, "case_id": case_id, "status": status,
           "duration": round(rep.duration, 3), "message": msg, "at": time.time()})


def pytest_sessionfinish(session, exitstatus):
    _emit({"type": "finished", "exitstatus": int(exitstatus)})
