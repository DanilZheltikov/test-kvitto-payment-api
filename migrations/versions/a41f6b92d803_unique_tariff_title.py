"""Make tariff seeding safe on repeated and concurrent application starts."""

from alembic import op


revision: str = "a41f6b92d803"
down_revision: str = "d8c041ee9d6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_tariffs_title", "tariffs", ["title"])


def downgrade() -> None:
    op.drop_constraint("uq_tariffs_title", "tariffs", type_="unique")
