"""add users and login codes

Passwordless email login (see app/services/auth.py): `users` (created on
first successful login) and `login_codes` (emailed one-time codes, stored
only as an HMAC hash).

Revision ID: a3f1c9d27b40
Revises: e49d32df7bd1
Create Date: 2026-09-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1c9d27b40'
down_revision: Union[str, Sequence[str], None] = 'e49d32df7bd1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('is_admin', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('login_codes',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('request_ip', sa.String(length=45), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_login_codes'))
    )
    op.create_index(op.f('ix_login_codes_email'), 'login_codes', ['email'], unique=False)
    op.create_index(op.f('ix_login_codes_request_ip'), 'login_codes', ['request_ip'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_login_codes_request_ip'), table_name='login_codes')
    op.drop_index(op.f('ix_login_codes_email'), table_name='login_codes')
    op.drop_table('login_codes')
    op.drop_table('users')
