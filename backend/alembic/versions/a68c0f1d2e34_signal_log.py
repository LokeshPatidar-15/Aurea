"""signal log

Revision ID: a68c0f1d2e34
Revises: 82d6e63c93fe
Create Date: 2026-11-18 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a68c0f1d2e34'
down_revision: Union[str, Sequence[str], None] = '82d6e63c93fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('signal_log',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('timeframe', sa.String(length=5), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('candle_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('direction', sa.SmallInteger(), nullable=False),
    sa.Column('signal', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('reference_price', sa.Float(), nullable=True),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_signal_log')),
    sa.UniqueConstraint('symbol', 'timeframe', 'kind', 'candle_time', name='uq_signal_log_candle')
    )
    op.create_index(op.f('ix_signal_log_candle_time'), 'signal_log', ['candle_time'], unique=False)
    op.create_index(op.f('ix_signal_log_symbol'), 'signal_log', ['symbol'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_signal_log_symbol'), table_name='signal_log')
    op.drop_index(op.f('ix_signal_log_candle_time'), table_name='signal_log')
    op.drop_table('signal_log')
