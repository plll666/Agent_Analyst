"""Добавить ``verifications.property_id``.

Колонки не было, а результат движка её содержит: без неё нельзя ответить на вопрос
«какое именно свойство нарушено», а прятать id внутрь ``statistics`` семантически
неверно — статистика описывает перебор, а не утверждение.

Nullable: у ``PENDING`` прогона свойство ещё не выбрано, у ``MODEL_INVALID`` модель
не дошла до выбора свойств. Требование описано в ``docs/API_CONTRACT.md`` §8.4.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_verifications_property_id"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Добавить колонку и индекс вместе с ``project_id``.

    Индекс нужен не ради скорости, а ради вопроса, который задаёт экран анализа:
    для проекта взять прогоны по конкретному свойству.
    """
    op.add_column(
        "verifications",
        sa.Column("property_id", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_verifications_project_property", "verifications", ["project_id", "property_id"]
    )


def downgrade() -> None:
    """Убрать колонку: без неё прогоны останутся, потеряется только привязка к свойству."""
    op.drop_index("ix_verifications_project_property", table_name="verifications")
    op.drop_column("verifications", "property_id")
