"""add comparison views

Every displayed comparison of 2+ cars, by car model - the basis of the
admin console's "most compared models" statistic (see
app/services/comparison_stats.py).

Revision ID: a8e4b1c7d052
Revises: f2b6a9d4c381
Create Date: 2026-10-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8e4b1c7d052'
down_revision: Union[str, Sequence[str], None] = 'f2b6a9d4c381'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PK = sa.BigInteger().with_variant(sa.Integer(), 'sqlite')


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('comparison_views',
    sa.Column('id', _PK, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_comparison_views'))
    )
    op.create_index(op.f('ix_comparison_views_created_at'), 'comparison_views', ['created_at'], unique=False)
    op.create_table('comparison_view_models',
    sa.Column('id', _PK, nullable=False),
    sa.Column('view_id', _PK, nullable=False),
    sa.Column('model_id', _PK, nullable=False),
    sa.Column('cars', sa.SmallInteger(), nullable=False),
    sa.ForeignKeyConstraint(['view_id'], ['comparison_views.id'], name=op.f('fk_comparison_view_models_view_id_comparison_views')),
    sa.ForeignKeyConstraint(['model_id'], ['models.id'], name=op.f('fk_comparison_view_models_model_id_models')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_comparison_view_models')),
    sa.UniqueConstraint('view_id', 'model_id', name=op.f('uq_comparison_view_models_view_id_model_id'))
    )
    op.create_index(op.f('ix_comparison_view_models_model_id'), 'comparison_view_models', ['model_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_comparison_view_models_model_id'), table_name='comparison_view_models')
    op.drop_table('comparison_view_models')
    op.drop_index(op.f('ix_comparison_views_created_at'), table_name='comparison_views')
    op.drop_table('comparison_views')
