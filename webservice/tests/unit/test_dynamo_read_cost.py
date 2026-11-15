"""DynamoDB 읽기량 시험 — 대시보드·관리자 요약이 같은 목록을 되풀이해 읽지 않아야 한다(프로비저닝 10 RCU 보호)."""
import boto3
import pytest
from moto import mock_aws

from app.services import admin_service, dashboard_service
from app.store.dynamo import DynamoStore, table_spec

REGION = "ap-northeast-2"
ALGOS = ["AES", "SHA-2", "SHA-3", "HMAC"]


class CountingTable:
    """Query 호출 횟수와 조건(Limit 여부)을 센다. 그 밖의 호출은 그대로 넘긴다."""
    def __init__(self, table):
        self._t, self.queries = table, []

    def query(self, **kw):
        self.queries.append(kw)
        return self._t.query(**kw)

    def __getattr__(self, name):
        return getattr(self._t, name)


@pytest.fixture()
def env(monkeypatch, tmp_path):
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(k, "testing")
    with mock_aws():
        boto3.client("dynamodb", region_name=REGION).create_table(**table_spec("rc"))
        table = boto3.resource("dynamodb", region_name=REGION).Table("rc")
        seed = DynamoStore(table)
        inst = seed.add_user("inst01", "x" * 60, "institution", "ORG")
        users = [seed.add_user(f"u{i:02d}", "x" * 60, "individual", None) for i in range(3)]
        apps = [seed.create_application(u.id, a) for u in users for a in ALGOS]
        for a in apps[::2]:
            seed.change_application_status(a.id, "submitted", "reviewing")
        c = seed.create_certificate(apps[0].id, "CAVP", "h" * 64, b"x", str(tmp_path))
        seed.set_tamper_status(c.id, "suspected")
        counting = CountingTable(table)
        yield DynamoStore(counting), counting, inst, users


def _app_queries(counting, pk=None):
    return [q for q in counting.queries if q["ExpressionAttributeValues"][":a" if ":a" in q["ExpressionAttributeValues"] else ":c"] == "APP#"
            and (pk is None or q["ExpressionAttributeValues"][":p"] == pk)]


def _cert_queries(counting):
    return [q for q in counting.queries if q["ExpressionAttributeValues"].get(":c") == "CERT#"]


def test_기관_대시보드는_신청_목록을_한_번만_읽는다(env):
    store, counting, inst, _ = env
    s = dashboard_service.get_summary(store, inst.id)
    assert len(_app_queries(counting)) <= 1 and len(_cert_queries(counting)) <= 1
    assert s["applications"]["total"] == 12 and s["certificates"]["suspected"] == 1


def test_관리자_요약은_신청_목록을_한_번만_읽는다(env):
    store, counting, inst, _ = env
    s = admin_service.get_summary(store, inst.id)
    assert len(_app_queries(counting)) <= 1 and len(_cert_queries(counting)) <= 1
    assert s["applications"]["total"] == 12


def test_최근_N건은_Limit으로_N건만_읽는다(env):
    store, counting, inst, _ = env
    got = store.recent_applications(None, 3)
    assert len(got) == 3
    qs = _app_queries(counting)
    assert len(qs) == 1 and qs[0].get("Limit") == 3
    ids = [a.id for a in got]
    assert ids == sorted(ids, reverse=True)


def test_쓰기_뒤에는_같은_저장소_객체도_새_값을_본다(env, tmp_path):
    store, counting, inst, users = env
    before = store.application_stats(None, __import__("datetime").datetime(2000, 1, 1))["total"]
    target = next(a for a in store.all_applications(None) if a.status == "reviewing")
    assert store.change_application_status(target.id, "reviewing", "approved")
    stats = store.application_stats(None, __import__("datetime").datetime(2000, 1, 1))
    assert stats["total"] == before and stats["by_status"].get("approved") == 1
    store.create_application(users[0].id, "RSA")
    assert store.application_stats(None, __import__("datetime").datetime(2000, 1, 1))["total"] == before + 1


class CountingClient:
    def __init__(self, client):
        self._c, self.batch = client, []

    def batch_get_item(self, **kw):
        self.batch.append(kw)
        return self._c.batch_get_item(**kw)

    def __getattr__(self, name):
        return getattr(self._c, name)


def test_기관_전체_집계는_최종_일관성_읽기로_비용을_반으로_줄인다(env):
    store, counting, inst, users = env
    dashboard_service.get_summary(store, inst.id)
    admin_service.get_summary(store, inst.id)
    agg = [q for q in counting.queries if q["ExpressionAttributeValues"][":p"] == "ALL"]
    assert agg and all(q["ConsistentRead"] is False for q in agg)


def test_개인_대시보드는_강한_일관성_읽기를_유지한다(env):
    store, counting, inst, users = env
    dashboard_service.get_summary(store, users[0].id)
    own = [q for q in counting.queries if q["ExpressionAttributeValues"][":p"].startswith("USER#")]
    assert own and all(q["ConsistentRead"] is True for q in own)


def test_목록_화면_조회는_강한_일관성을_유지한다(env):
    store, counting, inst, users = env
    store.list_applications(None, None, 1, 10)
    assert counting.queries[-1]["ConsistentRead"] is True


def test_여러_신청과_사용자는_한_번의_일괄_조회로_가져온다(env):
    store, counting, inst, users = env
    store.client = CountingClient(store.client)
    ids = {a.id for a in store.recent_applications(None, 5)}
    got = store.get_applications_by_ids(ids)
    assert set(got) == ids
    owners = store.get_users_by_ids({a.user_id for a in got.values()})
    assert set(owners) == {a.user_id for a in got.values()}
    assert len(store.client.batch) == 2  # 신청 한 번, 사용자 한 번(모두 있으면 재확인 없음)
    assert store.get_applications_by_ids({9999}) == {} and store.get_users_by_ids({9999}) == {}
    assert store.get_users_by_ids({True}) == {}


def test_일괄_조회는_100건_넘어도_나누어_모두_가져온다(env):
    store, counting, inst, users = env
    store.client = CountingClient(store.client)
    # 존재하지 않는 id 를 섞어 250개를 요청해도 있는 것만 돌려주고 호출은 100개 단위로 나뉜다
    got = store.get_applications_by_ids(set(range(1, 251)))
    assert len(got) == 12
    eventual = [b for b in store.client.batch if b["RequestItems"]["rc"]["ConsistentRead"] is False]
    assert len(eventual) == 3  # 없는 항목은 방금 쓴 것일 수 있어 강한 일관성으로 한 번 더 확인한다
    assert len(store.client.batch) > len(eventual)
