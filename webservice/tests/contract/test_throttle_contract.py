"""로그인 시도 제한 계약 시험 — 메모리 구현과 DynamoDB 구현이 같은 동작을 하는지 확인한다."""
import threading

import pytest

from app.store.dynamo import DynamoThrottle
from app.throttle import LoginThrottle
from tests.contract.conftest import REGION, serialize_moto


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture(params=["memory", "dynamo"])
def make_throttle(request, monkeypatch):
    clock = Clock()
    if request.param == "memory":
        yield lambda **kw: (LoginThrottle(clock=clock, **kw), clock)
        return
    import boto3
    from moto import mock_aws
    from app.store.dynamo import table_spec
    serialize_moto(monkeypatch)
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(k, "testing")
    with mock_aws():
        boto3.client("dynamodb", region_name=REGION).create_table(**table_spec("th"))
        table = lambda: boto3.resource("dynamodb", region_name=REGION).Table("th")
        yield lambda **kw: (DynamoThrottle(table, clock=clock, **kw), clock)


def test_한도까지만_허용하고_이후는_거부한다(make_throttle):
    th, _ = make_throttle(max_failures=5, window_seconds=900)
    assert [th.try_acquire("alice01") for _ in range(7)] == [True] * 5 + [False] * 2
    assert th.is_blocked("alice01")


def test_아이디는_대소문자를_구분하지_않고_서로_독립이다(make_throttle):
    th, _ = make_throttle(max_failures=2, window_seconds=900)
    assert th.try_acquire("ALICE01") and th.try_acquire("alice01")
    assert not th.try_acquire("Alice01")
    assert th.try_acquire("bob0001")


def test_시간이_지나면_풀리고_성공하면_초기화된다(make_throttle):
    th, clock = make_throttle(max_failures=3, window_seconds=900)
    for _ in range(3):
        th.try_acquire("alice01")
    assert th.is_blocked("alice01")
    clock.t += 901
    assert not th.is_blocked("alice01") and th.try_acquire("alice01")
    th.try_acquire("alice01"); th.try_acquire("alice01")
    assert th.is_blocked("alice01")
    th.reset("alice01")
    assert not th.is_blocked("alice01") and th.try_acquire("alice01")


def test_동시에_시도해도_한도를_넘지_못한다(make_throttle):
    th, _ = make_throttle(max_failures=5, window_seconds=900)
    results = []
    ts = [threading.Thread(target=lambda: results.append(th.try_acquire("racer01"))) for _ in range(24)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count(True) == 5 and results.count(False) == 19
