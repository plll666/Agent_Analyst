"""Подготовить прогон к агентному циклу: статус ошибки агента и модель без модели.

``AGENT_ERROR`` отделяет «агент не смог построить модель» от ``ENGINE_ERROR``
(движок не отработал) и от ``MODEL_INVALID`` (модель есть, но негодна). Без
отдельного значения эти три отказа выглядели бы одинаково, а фронт не смог бы
объяснить пользователю, что произошло.

``verifications.model_version_id`` становится nullable: в агентном цикле прогон
заводится до того, как модель построена, — её строит агент внутри задачи. Пока
модели нет, ссылка на неё пуста.

Старые прогоны и модели не меняются: колонка заполняется как раньше, а
``PENDING``-прогоны без модели появляются только с агентным циклом.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_agent_cycle"
down_revision: str | None = "0003_agent_explanations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = (
    "PENDING",
    "PROPERTY_HOLDS",
    "PROPERTY_VIOLATED",
    "MODEL_INVALID",
    "TIMEOUT",
    "STATE_LIMIT_REACHED",
    "ENGINE_ERROR",
    "AGENT_ERROR",
)


def upgrade() -> None:
    """Разрешить прогон без модели и добавить статус ошибки агента.

    Ограничение пересоздаётся прямым SQL: имя ``ck_verifications_status`` уже
    занято в базе, а ``op.create_check_constraint`` переписывает имя по
    соглашению именования и искал бы другое.
    """
    op.execute("ALTER TABLE verifications DROP CONSTRAINT ck_verifications_status")
    op.execute(
        "ALTER TABLE verifications ADD CONSTRAINT ck_verifications_status CHECK ("
        + "status IN (" + ", ".join(f"'{status}'" for status in STATUSES) + ")"
        + ")"
    )
    op.alter_column(
        "verifications",
        "model_version_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    """Вернуть прежние ограничения.

    Прогоны без модели удаляются: вернуть им ``NOT NULL`` иначе нельзя, а
    терять молча нельзя, поэтому downgrade их честно убирает.
    """
    op.execute("DELETE FROM verifications WHERE model_version_id IS NULL")
    op.alter_column(
        "verifications",
        "model_version_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=False,
    )
    op.execute("ALTER TABLE verifications DROP CONSTRAINT ck_verifications_status")
    op.execute(
        "ALTER TABLE verifications ADD CONSTRAINT ck_verifications_status CHECK ("
        + "status IN (" + ", ".join(f"'{status}'" for status in STATUSES[:-1]) + ")"
        + ")"
    )
