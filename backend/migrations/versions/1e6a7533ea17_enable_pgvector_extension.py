"""enable pgvector extension

Revision ID: 1e6a7533ea17
Revises: 90a50fb52b49
Create Date: 2026-08-11 19:06:04.563740

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e6a7533ea17'
down_revision: Union[str, None] = '90a50fb52b49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
