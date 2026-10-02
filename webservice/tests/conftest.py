import pathlib

import pytest

from app.db import init_db, make_engine, make_session_factory

_RED_FILE = pathlib.Path(__file__).parent / "red_cases.txt"


def _load_red() -> set[str]:
    if not _RED_FILE.exists():
        return set()
    return {l.strip() for l in _RED_FILE.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")}


def pytest_collection_modifyitems(config, items):
    """TDD Red 목록의 케이스는 xfail(strict): 실패해도 통과로 보고, 예기치 않게 통과하면 실패로 처리."""
    red = _load_red()
    for item in items:
        m = item.get_closest_marker("case")
        if m and m.args and m.args[0] in red:
            item.add_marker(pytest.mark.xfail(strict=True, raises=None,
                                              reason=f"TDD Red: {m.args[0]} 구현 전"))


@pytest.fixture()
def engine():
    eng = make_engine("sqlite://")
    init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    s = make_session_factory(engine)()
    yield s
    s.close()
