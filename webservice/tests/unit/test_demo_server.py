"""도구 시험: 시험 시연 서버(demo/) — 실행 관리·실시간 이벤트·API. 시험계획서 케이스(@case)가 아닌 배포·시연 도구의 검증."""
import sys
import time

import pytest

from app import create_app
from demo import runner as runner_mod
from demo import server as server_mod

SAMPLE = '''
import pytest

@pytest.mark.case("X-1")
def test_ok():
    assert True

@pytest.mark.case("X-2")
def test_bad():
    assert 1 == 2, "의도된 실패"

@pytest.mark.xfail(reason="red", strict=True)
@pytest.mark.case("X-3")
def test_red():
    assert False

def test_plain():
    pass
'''


@pytest.fixture()
def demo(tmp_path, monkeypatch):
    sample = tmp_path / "test_sample.py"
    sample.write_text(SAMPLE, encoding="utf-8")

    def builder(suite):
        if suite == "slow":
            return [sys.executable, "-c", "import time; time.sleep(3)"]
        return [sys.executable, "-m", "pytest", "-p", "demo.live_plugin", "-p", "no:cacheprovider", "-q",
                "-o", "addopts=", str(sample)]

    r = runner_mod.Runner(run_dir=tmp_path / "runs", command_builder=builder)
    monkeypatch.setattr(server_mod, "runner", r)
    monkeypatch.setitem(runner_mod.SUITES, "slow", ("느린 시험", []))
    return server_mod.app.test_client(), r


def wait_done(client, rid, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        s = client.get(f"/api/run/{rid}").get_json()
        if s["status"] != "running":
            return s
        time.sleep(0.3)
    raise AssertionError("시간 초과")


def test_build_command_per_suite():
    assert runner_mod.build_command("unit")[-1] == "tests/unit"
    assert runner_mod.build_command("all")[-1] == "tests"
    with pytest.raises(ValueError):
        runner_mod.build_command("nope")


def test_run_reports_each_case_status(demo):
    client, _ = demo
    rid = client.post("/api/run", json={"suite": "unit"}).get_json()["run_id"]
    s = wait_done(client, rid)
    assert s["status"] == "done"
    by = {r["case_id"] or r["nodeid"].split("::")[-1]: r["status"] for r in s["results"]}
    assert by == {"X-1": "pass", "X-2": "fail", "X-3": "red", "test_plain": "pass"}
    assert s["counts"] == {"pass": 2, "red": 1, "fail": 1, "skip": 0} and s["total"] == 4
    bad = next(r for r in s["results"] if r["case_id"] == "X-2")
    assert "의도된 실패" in bad["message"]
    assert client.get(f"/api/run/{rid}?since={s['next']}").get_json()["results"] == []


def test_only_one_run_at_a_time(demo):
    client, _ = demo
    first = client.post("/api/run", json={"suite": "slow"})
    assert first.status_code == 202
    second = client.post("/api/run", json={"suite": "unit"})
    assert second.status_code == 409 and second.get_json()["running"] == first.get_json()["run_id"]
    wait_done(client, first.get_json()["run_id"])
    assert client.post("/api/run", json={"suite": "unit"}).status_code == 202


def test_invalid_suite_and_unknown_run(demo):
    client, _ = demo
    assert client.post("/api/run", json={"suite": "rm -rf"}).status_code == 400
    assert client.get("/api/run/nope").status_code == 404


def test_shots_path_is_safe(demo):
    client, _ = demo
    rid = client.post("/api/run", json={"suite": "unit"}).get_json()["run_id"]
    wait_done(client, rid)
    assert client.get(f"/api/run/{rid}/shots/..%2Fevents.jsonl").status_code == 404
    assert client.get(f"/api/run/{rid}/shots/x.txt").status_code == 404


def test_index_and_health(demo):
    client, _ = demo
    html = client.get("/").get_data(as_text=True)
    assert "시험 시연 센터" in html and "data-suite=\"e2e\"" in html
    assert client.get("/healthz").get_json() == {"status": "ok"}


def test_service_healthz():
    c = create_app({"TESTING": True, "DATABASE_URL": "sqlite://", "SECRET_KEY": "x"}).test_client()
    r = c.get("/healthz")
    assert r.status_code == 200 and r.get_json() == {"status": "ok"}
