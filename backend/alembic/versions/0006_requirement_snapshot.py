"""Зафиксировать у прогона конкретную версию требования.

Без ссылки на требование воркер читал «текущую версию проекта» — и вход
уже поставленной задачи менялся от того, что пользователь успел сохранить
пока задача ждала в очереди. Постановка на проверку становится
воспроизводимой: прогон ссылается на тот текст, по которому запускался.

``NULL`` остаётся у старых прогонов: до этой миграции ссылку никто не писал,
и задача воркера по-прежнему читает текущую версию проекта. Данные не
мигрируются туда обратно: восстановить, какой текст был «текущим» в момент
старого прогона достоверно нельзя.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_requirement_snapshot"
down_revision: str | None = "0005_analysis_reasoning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Добавить ссылку прогона на выбранную версию требования."""
    op.add_column(
        "verifications",
        sa.Column("requirement_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_verifications_requirement_id_requirements",
        "verifications",
        "requirements",
        ["requirement_id"],
        ["id"],
    )
    op.create_index(
        "ix_verifications_requirement_id",
        "verifications",
        ["requirement_id"],
    )


def downgrade() -> None:
    """Убрать ссылку прогона на версию требования."""
    op.drop_index("ix_verifications_requirement_id", table_name="verifications")
    op.drop_column("verifications", "requirement_id")
