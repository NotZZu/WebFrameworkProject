"""저장소 계약 시험: 같은 시험을 모든 저장소 구현에 돌린다. (구현을 추가하려면 BACKENDS 와 make_factory 에 넣는다.)"""
import pytest

from app.db import init_db, make_engine, make_session_factory
from app.store import SqlStore

BACKENDS = ["sql"]


def make_factory(backend, tmp_path):
    """호출할 때마다 '요청 하나'에 해당하는 새 저장소를 돌려주는 함수."""
    if backend == "sql":
        engine = make_engine(f"sqlite:///{tmp_path / 'contract.db'}")
        init_db(engine)
        sf = make_session_factory(engine)
        return lambda: SqlStore(sf())
    raise ValueError(backend)


@pytest.fixture(params=BACKENDS)
def new_store(request, tmp_path):
    return make_factory(request.param, tmp_path)


@pytest.fixture()
def store(new_store):
    s = new_store()
    yield s
    s.close()
