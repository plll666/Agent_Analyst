"""Запомнить, включены ли были рассуждения модели у прогона.

Галочка на фронте — выбор пользователя, а не настройка сервера: один прогон
может быть с рассуждениями, другой без. Чтобы история не теряла этот факт,
режим хранится рядом с результатом.

``NULL`` означает «режим не выбирали»: старые прогоны и запуски, где провайдер
не умеет рассуждения, работали на умолчаниях провайдера. Это не то же самое,
что явное «выключено», поэтому колонка nullable, а не с ``server_default``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_analysis_reasoning"
down_revision: str | None = "0004_agent_cycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Добавить признак режима рассуждений."""
    op.add_column("verifications", sa.Column("reasoning", sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Убрать признак режима рассуждений."""
    op.drop_column("verifications", "reasoning")
