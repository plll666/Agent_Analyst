from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_verification_property_id"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Добавить колонку, которой требует ресурс Verification из API_CONTRACT.md §8.1.

    Nullable: у ``PENDING`` прогона и у ``MODEL_INVALID`` проверяемое свойство ещё не
    установлено, поэтому пустое значение законно.
    """
    op.add_column("verifications", sa.Column("property_id", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("verifications", "property_id")
