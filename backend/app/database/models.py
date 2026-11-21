import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.execution import ExecutionStatus
from app.domain.verification import ROOT_CAUSES, VerificationStatus

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

VERIFICATION_STATUSES = tuple(str(status) for status in VerificationStatus)
EXECUTION_STATUSES = tuple(str(state) for state in ExecutionStatus)
IMPORT_FORMATS = ("txt", "docx")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(
        Text,
        comment="Argon2id, соль внутри формата хеша",
    )
    display_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_users_email_lower", text("lower(email)"), unique=True),)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_projects_owner_id", "owner_id"),)


class RequirementImport(Base):
    """Загруженный файл требования: извлечённый текст и фрагменты.

    Импорт — не версия требования: он лишь предпросмотр. Версию создаёт
    пользователь, подтвердив текст (``requirements.source_import_id``).
    """

    __tablename__ = "requirement_imports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    filename: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(8))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(CHAR(64))
    raw_text: Mapped[str] = mapped_column(Text)
    fragments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    # Ссылка на файл в локальном хранилище; наружу не выдаётся.
    storage_uri: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("format IN ('txt', 'docx')", name="ck_requirement_imports_format"),
        Index("ix_requirement_imports_project_created", "project_id", text("created_at DESC")),
    )


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    version: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    paragraph_ref: Mapped[str | None] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Происхождение текста: из какого импорта подтверждён и менялся ли он
    # относительно извлечённого. ``fragments`` — фрагменты именно этой версии,
    # по ним подсвечиваются цитаты агента.
    source_import_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("requirement_imports.id", ondelete="SET NULL")
    )
    source_modified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    fragments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_requirements_project_version", "project_id", text("version DESC")),)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("model_versions.id"))
    version: Mapped[int] = mapped_column(Integer)
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("requirements.id"))
    source: Mapped[str] = mapped_column(String(20))
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)
    schema_hash: Mapped[str] = mapped_column(CHAR(64))
    validation_status: Mapped[str] = mapped_column(String(20))
    validation_errors: Mapped[list[str] | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("source IN ('agent', 'manual')", name="ck_model_versions_source"),
        Index("ix_model_versions_project_version", "project_id", text("version DESC")),
        Index("ix_model_versions_parent_version_id", "parent_version_id"),
        Index("ix_model_versions_requirement_id", "requirement_id"),
    )


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("model_versions.id"))
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("requirements.id"))
    status: Mapped[str] = mapped_column(String(32))
    property_id: Mapped[str | None] = mapped_column(String(32))
    engine: Mapped[str] = mapped_column(String(32))
    engine_version: Mapped[str | None] = mapped_column(String(64))
    counterexample: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    statistics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    related_requirements: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_detail: Mapped[str | None] = mapped_column(Text)
    business_summary: Mapped[str] = mapped_column(Text)
    hypothesis: Mapped[str | None] = mapped_column(Text)
    question: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(String(32))
    reasoning: Mapped[bool | None] = mapped_column(Boolean)
    model_auto_edited: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Состояние выполнения отдельно от логического результата: пока задача
    # стоит в очереди или работает, ``status = PENDING``, а ``execution_status``
    # показывает, что сейчас происходит (контракт спринта 3, раздел 4).
    execution_status: Mapped[str] = mapped_column(
        String(16), server_default=text("'QUEUED'"), comment="QUEUED/RUNNING/CANCELLING/COMPLETED/FAILED/CANCELLED"
    )
    input_key: Mapped[str | None] = mapped_column(
        String(71), comment="sha256:... зафиксированного входа; NULL у старых прогонов"
    )
    run_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_seq: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in VERIFICATION_STATUSES) + ")",
            name="ck_verifications_status",
        ),
        CheckConstraint(
            "execution_status IN ("
            + ", ".join(f"'{s}'" for s in EXECUTION_STATUSES)
            + ")",
            name="ck_verifications_execution_status",
        ),
        CheckConstraint("model_auto_edited = false", name="ck_verifications_model_auto_edited"),
        CheckConstraint(
            "root_cause IS NULL OR root_cause IN ("
            + ", ".join(f"'{cause}'" for cause in ROOT_CAUSES)
            + ")",
            name="ck_verifications_root_cause",
        ),
        Index("ix_verifications_project_created", "project_id", text("created_at DESC")),
        Index("ix_verifications_model_version_id", "model_version_id"),
        Index("ix_verifications_requirement_id", "requirement_id"),
        Index("ix_verifications_project_property", "project_id", "property_id"),
        Index("ix_verifications_project_input_key", "project_id", "input_key"),
    )


class VerificationEvent(Base):
    """Сохранённое событие этапа или состояния прогона.

    Источник истины для истории и для SSE: ``seq`` монотонен в пределах
    прогона, поэтому повторная доставка определяется парой
    ``(verification_id, seq)`` и не создаёт дублей на фронте.
    """

    __tablename__ = "verification_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    verification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("verifications.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    # Идентификатор этапа для событий stage.*; пусто у событий состояния прогона.
    stage_id: Mapped[str | None] = mapped_column(String(128))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("verification_id", "seq", name="uq_verification_events_run_seq"),
        Index("ix_verification_events_run_seq", "verification_id", "seq"),
        Index("ix_verification_events_run_stage", "verification_id", "stage_id"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("model_versions.id"))
    verification_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("verifications.id"))
    kind: Mapped[str] = mapped_column(String(32))
    storage_uri: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(CHAR(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_artifacts_project_kind", "project_id", "kind"),)
