"""add saved requirements

A logged-in user's most recent StructuredRequirements snapshot (see
app/models/saved_requirements.py), so the "Technické požadavky" drawer
survives a page reload / a new login session - app/services/
conversation.py's conversation state is otherwise purely in-memory.

Note: autogenerate also proposed `alter_column` type changes on several
unrelated existing FK columns (BIGINT -> BigInteger().with_variant(...,
'sqlite')) - a pre-existing diffing artifact of those columns not using
BigIntPK (only primary keys do), not caused by this change. Left out here
deliberately; they're no-ops on SQLite either way.

Revision ID: e4c033fa27c0
Revises: a3f1c9d27b40
Create Date: 2026-09-22 17:50:08.830347

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4c033fa27c0'
down_revision: Union[str, Sequence[str], None] = 'a3f1c9d27b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('saved_requirements',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('requirements_json', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_saved_requirements_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_saved_requirements')),
    sa.UniqueConstraint('user_id', name=op.f('uq_saved_requirements_user_id'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('saved_requirements')
