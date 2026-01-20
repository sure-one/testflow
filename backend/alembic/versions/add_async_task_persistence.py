"""add async task persistence table

Revision ID: add_async_task
Revises:
Create Date: 2026-01-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = 'add_async_task'
down_revision = 'faf9a428a751'  # 依赖于上一个迁移
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 async_tasks 表"""
    # 创建 async_tasks 表
    op.create_table(
        'async_tasks',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('task_id', sa.String(length=100), nullable=False),
        sa.Column('task_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', 'cancelled', 'timeout', name='asynctaskstatus'), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('total_batches', sa.Integer(), nullable=False),
        sa.Column('completed_batches', sa.Integer(), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # 创建索引
    op.create_index('ix_async_tasks_task_id', 'async_tasks', ['task_id'], unique=True)
    op.create_index('ix_async_tasks_task_type', 'async_tasks', ['task_type'], unique=False)
    op.create_index('ix_async_tasks_status', 'async_tasks', ['status'], unique=False)
    op.create_index('ix_async_tasks_user_id', 'async_tasks', ['user_id'], unique=False)
    op.create_index('ix_async_tasks_created_at', 'async_tasks', ['created_at'], unique=False)
    op.create_index('idx_async_tasks_status_created', 'async_tasks', ['status', 'created_at'], unique=False)
    op.create_index('idx_async_tasks_user_status', 'async_tasks', ['user_id', 'status'], unique=False)


def downgrade() -> None:
    """删除 async_tasks 表"""
    op.drop_table('async_tasks')
