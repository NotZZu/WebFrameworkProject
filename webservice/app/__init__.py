"""자동화 검증시스템 웹 서비스 (TDD Green 단계 진행 중 — SC-01 인증 구현 완료)."""
import os

from flask import Flask

from .db import init_db, make_engine, make_session_factory
from .store import SqlStore
from .throttle import LoginThrottle

_DEV_SECRET = "dev-secret-change-me"
_DEV_PSEUDONYM_SECRET = "dev-pseudonym-secret"


def _setup_dynamodb(app: Flask) -> None:
    """서버리스 배포: 데이터와 로그인 시도 횟수를 DynamoDB 한 테이블에 둔다. boto3 는 이때만 불러온다."""
    import threading

    import boto3

    from .store.dynamo import DynamoStore, DynamoThrottle

    name = app.config["DYNAMODB_TABLE"]
    if not name:
        raise RuntimeError("DYNAMODB_TABLE 환경변수를 설정해야 합니다.")
    local = threading.local()  # boto3 리소스는 스레드 간 공유할 수 없으므로 스레드마다 하나씩 쓴다

    def table():
        if not hasattr(local, "table"):
            local.table = boto3.resource("dynamodb").Table(name)
        return local.table
    app.store_factory = lambda: DynamoStore(table())
    app.login_throttle = DynamoThrottle(table)


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        STORE_BACKEND=os.environ.get("STORE_BACKEND", "sql"),   # sql | dynamodb
        DYNAMODB_TABLE=os.environ.get("DYNAMODB_TABLE", ""),
        DATABASE_URL=os.environ.get("DATABASE_URL", "sqlite:///app.db"),
        SECRET_KEY=os.environ.get("SECRET_KEY", _DEV_SECRET),
        PSEUDONYM_SECRET=os.environ.get("PSEUDONYM_SECRET", _DEV_PSEUDONYM_SECRET),
        CERT_STORAGE_DIR=os.environ.get("CERT_STORAGE_DIR", "storage/certs"),
        TESTING=False,
        MAX_CONTENT_LENGTH=64 * 1024,  # 요청 본문 상한(DF-06)
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # 기본은 HTTPS 에서만 쿠키 전송(DF-09). 로컬 개발은 COOKIE_SECURE=0 으로 끈다.
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") != "0",
    )
    if config:
        app.config.update(config)
    if app.config["SESSION_COOKIE_SECURE"] and app.config["TESTING"]:
        app.config["SESSION_COOKIE_SECURE"] = bool((config or {}).get("SESSION_COOKIE_SECURE", False))
    if not app.config["TESTING"] and os.environ.get("FLASK_DEBUG") != "1":
        for key, dev_value in (("SECRET_KEY", _DEV_SECRET), ("PSEUDONYM_SECRET", _DEV_PSEUDONYM_SECRET)):
            if app.config[key] in ("", dev_value):  # 개발용 기본 키로는 기동하지 않는다(DF-04)
                raise RuntimeError(f"{key} 환경변수를 설정해야 합니다.")
    if app.config["STORE_BACKEND"] == "dynamodb":
        _setup_dynamodb(app)
    elif app.config["STORE_BACKEND"] == "sql":
        app.login_throttle = LoginThrottle()
        app.engine = make_engine(app.config["DATABASE_URL"])
        app.session_factory = make_session_factory(app.engine)
        init_db(app.engine)
        app.store_factory = lambda: SqlStore(app.session_factory())
    else:
        raise RuntimeError("STORE_BACKEND 는 sql 또는 dynamodb 여야 합니다.")

    from .api import auth as auth_api
    from .api import cavp as cavp_api
    from .api import certificates as certificates_api
    from .api import dashboard as dashboard_api
    from .api import privacy as privacy_api
    from .api.helpers import register_error_handlers
    from . import pages

    app.register_blueprint(auth_api.bp)
    app.register_blueprint(cavp_api.bp)
    app.register_blueprint(certificates_api.bp)
    app.register_blueprint(dashboard_api.bp)
    app.register_blueprint(privacy_api.bp)
    app.register_blueprint(pages.bp)
    register_error_handlers(app)

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp
    return app
