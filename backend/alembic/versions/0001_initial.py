"""initial TrustDesk schema

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.database import Base
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    pass
