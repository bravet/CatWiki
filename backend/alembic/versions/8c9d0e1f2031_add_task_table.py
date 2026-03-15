"""add task table for asynchronous jobs

Revision ID: 8c9d0e1f2031
Revises: 63b263450d2f
Create Date: 2026-03-15 12:05:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "8c9d0e1f2031"
down_revision = "7a8b9c0d1e2f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False, comment="所属租户ID"),
        sa.Column("site_id", sa.Integer(), nullable=True, comment="所属站点ID"),
        sa.Column("task_type", sa.String(length=50), nullable=False, comment="任务类型"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="任务状态"),
        sa.Column("job_id", sa.String(length=100), nullable=True, comment="Arq Job ID"),
        sa.Column("progress", sa.Float(), nullable=False, comment="进度 (0.0 - 100.0)"),
        sa.Column("payload", sa.JSON(), nullable=True, comment="任务参数"),
        sa.Column("result", sa.JSON(), nullable=True, comment="执行结果"),
        sa.Column("error", sa.Text(), nullable=True, comment="错误信息"),
        sa.Column("created_by", sa.String(length=100), nullable=False, comment="创建者"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_id"), "task", ["id"], unique=False)
    op.create_index(op.f("ix_task_tenant_id"), "task", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_task_site_id"), "task", ["site_id"], unique=False)
    op.create_index(op.f("ix_task_task_type"), "task", ["task_type"], unique=False)
    op.create_index(op.f("ix_task_status"), "task", ["status"], unique=False)
    op.create_index(op.f("ix_task_job_id"), "task", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_task_job_id"), table_name="task")
    op.drop_index(op.f("ix_task_status"), table_name="task")
    op.drop_index(op.f("ix_task_task_type"), table_name="task")
    op.drop_index(op.f("ix_task_site_id"), table_name="task")
    op.drop_index(op.f("ix_task_tenant_id"), table_name="task")
    op.drop_index(op.f("ix_task_id"), table_name="task")
    op.drop_table("task")
