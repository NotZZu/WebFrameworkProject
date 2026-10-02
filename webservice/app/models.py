"""ORM 모델 — 시스템설계서 v1.1 5.2절 테이블 정의와 컬럼 단위로 대응."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _enum(*values, name):
    return Enum(*values, name=name, native_enum=False, create_constraint=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    user_type: Mapped[str] = mapped_column(_enum("individual", "company", "institution", name="user_type"))
    org_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PersonalInfo(Base):
    __tablename__ = "personal_info"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)  # users 1:1
    pseudonym_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    anonymization_level: Mapped[str] = mapped_column(_enum("pseudonym", "anonymous", name="anon_level"))
    masked_display_value: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CavpApplication(Base):
    __tablename__ = "cavp_applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    algorithm_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        _enum("submitted", "reviewing", "approved", "rejected", name="app_status"),
        default="submitted",
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Certificate(Base):
    __tablename__ = "certificates"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("cavp_applications.id"))
    cert_type: Mapped[str] = mapped_column(_enum("CAVP", "KCMVP", name="cert_type"))
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    integrity_hash: Mapped[str] = mapped_column(String(128))
    tamper_status: Mapped[str] = mapped_column(
        _enum("normal", "suspected", name="tamper_status"), default="normal"
    )
