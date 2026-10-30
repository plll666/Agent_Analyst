"""Добавить класс причины контрпримера и связь модели с версией требования.

``verifications.root_cause`` хранит гипотезу агента о причине нарушения: ошибка в
требованиях, ошибка интерпретации или отсутствующее правило. Без отдельной колонки
три класса из кейса остались бы прозой внутри ``hypothesis`` и не проверялись бы.

``model_versions.requirement_id`` нужен, чтобы объяснение ссылалось на тот текст,
по которому модель строилась: без связи шаг объяснения читал бы текущее требование
проекта, а оно могло смениться после построения модели.

Обе колонки nullable: у прогонов без нарушения причины нет, у моделей, созданных до
этой миграции, источник неизвестен.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_agent_explanations"
down_revision: str | None = "0002_verifications_property_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROOT_CAUSES = ("REQUIREMENT_ERROR", "AGENT_ERROR", "MISSING_RULE")


def upgrade() -> None:
    """Добавить колонки, ограничение и индексы."""
    op.add_column(
        "verifications",
        sa.Column("root_cause", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "ck_verifications_root_cause",
        "verifications",
        "root_cause IS NULL OR root_cause IN ("
        + ", ".join(f"'{cause}'" for cause in ROOT_CAUSES)
        + ")",
    )

    op.add_column(
        "model_versions",
        sa.Column("requirement_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_model_versions_requirement_id_requirements",
        "model_versions",
        "requirements",
        ["requirement_id"],
        ["id"],
    )
    op.create_index("ix_model_versions_requirement_id", "model_versions", ["requirement_id"])


def downgrade() -> None:
    """Убрать связь и класс причины: результаты и модели останутся на месте."""
    op.drop_index("ix_model_versions_requirement_id", table_name="model_versions")
    op.drop_constraint(
        "fk_model_versions_requirement_id_requirements", "model_versions", type_="foreignkey"
    )
    op.drop_column("model_versions", "requirement_id")

    op.drop_constraint("ck_verifications_root_cause", "verifications", type_="check")
    op.drop_column("verifications", "root_cause")
