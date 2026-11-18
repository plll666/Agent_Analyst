"""Спринт 3: импорт требований, состояния выполнения и события этапов.

Три изменения одного спринта в одной миграции — они описывают один и тот же
контракт (``sprint_3_contracts.md``) и разносятся по отдельным релизам не
имеют смысла:

1. ``requirement_imports`` — загруженные файлы; у ``requirements`` появляются
   ссылка на источник, признак изменения текста и фрагменты версии.
2. У ``verifications`` — состояние выполнения (``execution_status``), ключ
   входа (``input_key``), время старта/финиша и счётчик событий. Существующие
   строки заполняются по логическому ``status``: PENDING — это QUEUED,
   терминальный успех — COMPLETED, остальное — FAILED.
3. ``verification_events`` — история этапов для API и SSE.

``CANCELLED`` добавляется в CHECK статуса: без него отменённый прогон не
записался бы ни в одну строку.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_sprint3_execution"
down_revision: str | None = "0006_requirement_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_VALUES = ", ".join(
    f"'{value}'" for value in (
        "PENDING", "PROPERTY_HOLDS", "PROPERTY_VIOLATED", "MODEL_INVALID",
        "TIMEOUT", "STATE_LIMIT_REACHED", "ENGINE_ERROR", "AGENT_ERROR", "CANCELLED",
    )
)
_EXECUTION_VALUES = ", ".join(
    f"'{value}'" for value in (
        "QUEUED", "RUNNING", "CANCELLING", "COMPLETED", "FAILED", "CANCELLED",
    )
)


def upgrade() -> None:
    """Создать импорт и события, добавить состояния выполнения и CANCELLED."""
    _create_imports()
    _add_requirement_source()
    _add_execution_columns()
    _allow_cancelled_status()
    _create_events()


def downgrade() -> None:
    """Снять спринт 3: история и состояния уходят, данные не возвращаются."""
    op.drop_table("verification_events")
    op.execute("ALTER TABLE verifications DROP CONSTRAINT ck_verifications_ck_verifications_status")
    old_values = ", ".join(f"'{value}'" for value in (
        "PENDING", "PROPERTY_HOLDS", "PROPERTY_VIOLATED", "MODEL_INVALID",
        "TIMEOUT", "STATE_LIMIT_REACHED", "ENGINE_ERROR", "AGENT_ERROR",
    ))
    op.execute("ALTER TABLE verifications ADD CONSTRAINT ck_verifications_ck_verifications_status "
               f"CHECK (status IN ({old_values}))")
    op.execute("ALTER TABLE verifications DROP CONSTRAINT ck_verifications_execution_status")
    op.drop_index("ix_verifications_project_input_key", table_name="verifications")
    op.drop_column("verifications", "last_event_seq")
    op.drop_column("verifications", "finished_at")
    op.drop_column("verifications", "started_at")
    op.drop_column("verifications", "input_key")
    op.drop_column("verifications", "run_config")
    op.drop_column("verifications", "execution_status")
    op.drop_constraint(
        "fk_requirements_source_import_id_requirement_imports",
        "requirements",
        type_="foreignkey",
    )
    op.drop_column("requirements", "fragments")
    op.drop_column("requirements", "source_modified")
    op.drop_column("requirements", "source_import_id")
    op.drop_table("requirement_imports")


def _create_imports() -> None:
    """Файлы импорта с извлечённым текстом и фрагментами."""
    op.create_table(
        "requirement_imports",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("fragments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("format IN ('txt', 'docx')", name="ck_requirement_imports_format"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_requirement_imports_project_id_projects"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_requirement_imports_created_by_users"),
        sa.PrimaryKeyConstraint("id", name="pk_requirement_imports"),
    )
    op.create_index(
        "ix_requirement_imports_project_created",
        "requirement_imports",
        ["project_id", sa.text("created_at DESC")],
    )


def _add_requirement_source() -> None:
    """Связь версии требования с импортом и фрагменты этой версии."""
    op.add_column(
        "requirements",
        sa.Column("source_import_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "requirements",
        sa.Column(
            "source_modified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "requirements",
        sa.Column("fragments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        "fk_requirements_source_import_id_requirement_imports",
        "requirements",
        "requirement_imports",
        ["source_import_id"],
        ["id"],
        ondelete="SET NULL",
    )


def _add_execution_columns() -> None:
    """Состояние выполнения, ключ входа, время и счётчик событий."""
    op.add_column(
        "verifications",
        sa.Column(
            "execution_status",
            sa.String(length=16),
            server_default=sa.text("'QUEUED'"),
            nullable=False,
        ),
    )
    op.add_column("verifications", sa.Column("input_key", sa.String(length=71), nullable=True))
    op.add_column("verifications", sa.Column("run_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column(
        "verifications", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "verifications", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "verifications",
        sa.Column("last_event_seq", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    # Существующие строки: PENDING = стоит в очереди, успех = завершён,
    # остальное = провал. Время финиша достоверно неизвестно, поэтому NULL.
    op.execute(
        "UPDATE verifications SET execution_status = CASE "
        "WHEN status = 'PENDING' THEN 'QUEUED' "
        "WHEN status IN ('PROPERTY_HOLDS', 'PROPERTY_VIOLATED') THEN 'COMPLETED' "
        "WHEN status = 'CANCELLED' THEN 'CANCELLED' "
        "ELSE 'FAILED' END"
    )
    op.execute("ALTER TABLE verifications ADD CONSTRAINT ck_verifications_execution_status "
               f"CHECK (execution_status IN ({_EXECUTION_VALUES}))")
    op.create_index(
        "ix_verifications_project_input_key",
        "verifications",
        ["project_id", "input_key"],
    )


def _allow_cancelled_status() -> None:
    """Разрешить ``CANCELLED`` в логическом статусе прогона."""
    op.execute("ALTER TABLE verifications DROP CONSTRAINT ck_verifications_ck_verifications_status")
    op.execute("ALTER TABLE verifications ADD CONSTRAINT ck_verifications_ck_verifications_status "
               f"CHECK (status IN ({_STATUS_VALUES}))")


def _create_events() -> None:
    """История событий этапов и состояния прогона."""
    op.create_table(
        "verification_events",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("verification_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("stage_id", sa.String(length=128), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["verification_id"],
            ["verifications.id"],
            name="fk_verification_events_verification_id_verifications",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_verification_events"),
        sa.UniqueConstraint("verification_id", "seq", name="uq_verification_events_run_seq"),
    )
    op.create_index(
        "ix_verification_events_run_seq", "verification_events", ["verification_id", "seq"]
    )
    op.create_index(
        "ix_verification_events_run_stage", "verification_events", ["verification_id", "stage_id"]
    )
