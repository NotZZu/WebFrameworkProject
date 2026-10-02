"""자동화 검증시스템 웹 서비스 (TDD Green 단계 진행 중 — SC-01 인증 구현 완료)."""
import os

from flask import Flask

from .db import init_db, make_engine, make_session_factory


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        DATABASE_URL=os.environ.get("DATABASE_URL", "sqlite:///app.db"),
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
        PSEUDONYM_SECRET=os.environ.get("PSEUDONYM_SECRET", "dev-pseudonym-secret"),
        CERT_STORAGE_DIR=os.environ.get("CERT_STORAGE_DIR", "storage/certs"),
        TESTING=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if config:
        app.config.update(config)
    app.engine = make_engine(app.config["DATABASE_URL"])
    app.session_factory = make_session_factory(app.engine)
    init_db(app.engine)

    from .api import auth as auth_api
    from .api import dashboard as dashboard_api
    from .api.helpers import register_error_handlers
    from . import pages

    app.register_blueprint(auth_api.bp)
    app.register_blueprint(dashboard_api.bp)
    app.register_blueprint(pages.bp)
    register_error_handlers(app)
    return app
