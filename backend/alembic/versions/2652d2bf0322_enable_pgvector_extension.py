"""enable pgvector extension

Revision ID: 2652d2bf0322
Revises: 7c4cea4a14df
Create Date: 2026-07-23 23:25:32.819346

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2652d2bf0322'
down_revision: Union[str, None] = '7c4cea4a14df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
