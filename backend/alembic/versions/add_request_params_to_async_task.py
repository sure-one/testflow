"""add request_params to async_task

Revision ID: add_request_params
Revises: add_async_task
Create Date: 2026-02-10

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'add_request_params'
down_revision = 'add_async_task'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """添加 request_params 字段到 async_tasks 表"""
    op.add_column('async_tasks',
        sa.Column('request_params', sa.JSON(), nullable=True, comment='原始请求参数，用于重试')
    )


def downgrade() -> None:
    """移除 request_params 字段"""
    op.drop_column('async_tasks', 'request_params')
