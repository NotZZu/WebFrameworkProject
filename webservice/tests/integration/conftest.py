import pytest

from app import create_app
from tests import factories


@pytest.fixture()
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE_URL": "sqlite://",
        "SECRET_KEY": "test-secret",
        "PSEUDONYM_SECRET": "test-pseudonym",
        "CERT_STORAGE_DIR": str(tmp_path / "certs"),
    })


@pytest.fixture()
def db(app):
    s = app.session_factory()
    yield s
    s.close()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_client(app):
    """서로 다른 쿠키 jar 를 가진 클라이언트(다중 사용자 시나리오용)."""
    return lambda: app.test_client()


def login(client, username, password=factories.DEFAULT_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


@pytest.fixture()
def login_as(db, make_client):
    """login_as(user_type='individual') → (client, user). factories 로 만든 사용자로 실제 로그인 API 호출."""
    def _login_as(user_type="individual", username=None):
        user = factories.make_user(db, username=username, user_type=user_type)
        c = make_client()
        r = login(c, user.username)
        assert r.status_code == 200, "로그인 API 미구현 또는 실패 — 전제 조건 위반"
        return c, user
    return _login_as
