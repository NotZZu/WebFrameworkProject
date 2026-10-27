"""저장소 계약 시험: 같은 시험을 모든 저장소 구현에 돌린다. (구현을 추가하려면 BACKENDS 와 make_factory 에 넣는다.)"""
import os

import pytest

from app.db import init_db, make_engine, make_session_factory
from app.store import SqlStore

BACKENDS = ["sql", "dynamo"]
REGION = "ap-northeast-2"


def serialize_moto(monkeypatch):
    """moto(로컬 흉내 환경)는 스레드 안전하지 않아 동시에 호출하면 자체 오류("dictionary changed size")가 난다.
    진짜 DynamoDB 는 항목 단위로 원자적이므로, 흉내 환경의 '한 번의 API 호출'만 순서대로 처리되게 잠근다.
    우리 코드의 여러 호출(읽고 → 쓰기) 사이에는 여전히 다른 스레드가 끼어들 수 있다."""
    import threading
    from moto.dynamodb.responses import DynamoHandler
    lock, orig = threading.RLock(), DynamoHandler.call_action

    def locked(self, *a, **k):
        with lock:
            return orig(self, *a, **k)
    monkeypatch.setattr(DynamoHandler, "call_action", locked)


def make_factory(backend, tmp_path):
    """호출할 때마다 '요청 하나'에 해당하는 새 저장소를 돌려주는 함수."""
    if backend == "sql":
        engine = make_engine(f"sqlite:///{tmp_path / 'contract.db'}")
        init_db(engine)
        sf = make_session_factory(engine)
        return lambda: SqlStore(sf())
    if backend == "dynamo":
        import boto3
        from app.store.dynamo import DynamoStore, table_spec
        boto3.client("dynamodb", region_name=REGION).create_table(**table_spec("contract"))
        # 스레드마다 자기 리소스를 쓰도록 호출할 때마다 새로 만든다(boto3 리소스는 스레드 간 공유 불가)
        return lambda: DynamoStore(boto3.resource("dynamodb", region_name=REGION).Table("contract"))
    raise ValueError(backend)


@pytest.fixture(params=BACKENDS)
def new_store(request, tmp_path, monkeypatch):
    if request.param == "dynamo":
        from moto import mock_aws
        serialize_moto(monkeypatch)
        for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
            monkeypatch.setenv(k, "testing")
        with mock_aws():
            yield make_factory("dynamo", tmp_path)
    else:
        yield make_factory(request.param, tmp_path)


@pytest.fixture()
def store(new_store):
    s = new_store()
    yield s
    s.close()
