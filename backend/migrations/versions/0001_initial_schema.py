"""initial schema

設計書：テーブル定義（models）_v0.2.0.md

Revision ID: 0001
Revises:
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "EQUIPMENT",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asset_number", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=500), server_default="", nullable=False),
        sa.Column("location", sa.String(length=100), server_default="", nullable=False),
        sa.Column("active_flag", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_number", name="uq_equipment_asset_number"),
    )
    op.create_index("idx_equipment_active_flag", "EQUIPMENT", ["active_flag"], unique=False)
    op.create_index("idx_equipment_asset_number", "EQUIPMENT", ["asset_number"], unique=False)
    op.create_index("idx_equipment_category", "EQUIPMENT", ["category"], unique=False)

    op.create_table(
        "USER",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("department", sa.String(length=50), server_default="", nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(), server_default="一般", nullable=False),
        sa.Column("active_flag", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "password_change_required_flag", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("token_generation", sa.Integer(), server_default="0", nullable=False),
        sa.Column("login_failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('一般', '管理者')", name="ck_user_role"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_user_id"),
    )
    op.create_index("idx_user_user_id", "USER", ["user_id"], unique=False)

    op.create_table(
        "LOAN_REQUEST",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("applicant_user_id", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("purpose", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(), server_default="申請中", nullable=False),
        sa.Column("reject_cancel_reason", sa.String(length=200), server_default="", nullable=False),
        sa.Column("approved_rejected_by_user_id", sa.Integer(), nullable=True),
        sa.Column("lent_by_user_id", sa.Integer(), nullable=True),
        sa.Column("returned_by_user_id", sa.Integer(), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("approved_rejected_at", sa.DateTime(), nullable=True),
        sa.Column("lent_at", sa.DateTime(), nullable=True),
        sa.Column("returned_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("return_note", sa.String(length=200), server_default="", nullable=False),
        sa.CheckConstraint(
            "status IN ('申請中', '承認済み', '貸出中', '返却済み', '却下', '取消')",
            name="ck_loan_request_status",
        ),
        sa.ForeignKeyConstraint(
            ["applicant_user_id"],
            ["USER.id"],
            name="fk_loan_request_applicant_user_id",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_rejected_by_user_id"],
            ["USER.id"],
            name="fk_loan_request_approved_rejected_by",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by_user_id"],
            ["USER.id"],
            name="fk_loan_request_cancelled_by",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["EQUIPMENT.id"],
            name="fk_loan_request_equipment_id",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lent_by_user_id"],
            ["USER.id"],
            name="fk_loan_request_lent_by",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["returned_by_user_id"],
            ["USER.id"],
            name="fk_loan_request_returned_by",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_loan_request_applicant_user_id", "LOAN_REQUEST", ["applicant_user_id"], unique=False)
    op.create_index("idx_loan_request_equipment_id", "LOAN_REQUEST", ["equipment_id"], unique=False)
    op.create_index("idx_loan_request_status", "LOAN_REQUEST", ["status"], unique=False)

    op.create_table(
        "NOTIFICATION",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.String(), nullable=False),
        sa.Column("loan_request_id", sa.Integer(), nullable=False),
        sa.Column("read_flag", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "notification_type IN ('承認', '却下', '取消', '新規申請', '返却期限')",
            name="ck_notification_type",
        ),
        sa.ForeignKeyConstraint(
            ["loan_request_id"],
            ["LOAN_REQUEST.id"],
            name="fk_notification_loan_request_id",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["USER.id"],
            name="fk_notification_recipient_user_id",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_notification_loan_request_id", "NOTIFICATION", ["loan_request_id"], unique=False)
    op.create_index("idx_notification_read_flag", "NOTIFICATION", ["read_flag"], unique=False)
    op.create_index("idx_notification_recipient_user_id", "NOTIFICATION", ["recipient_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_notification_recipient_user_id", table_name="NOTIFICATION")
    op.drop_index("idx_notification_read_flag", table_name="NOTIFICATION")
    op.drop_index("idx_notification_loan_request_id", table_name="NOTIFICATION")
    op.drop_table("NOTIFICATION")

    op.drop_index("idx_loan_request_status", table_name="LOAN_REQUEST")
    op.drop_index("idx_loan_request_equipment_id", table_name="LOAN_REQUEST")
    op.drop_index("idx_loan_request_applicant_user_id", table_name="LOAN_REQUEST")
    op.drop_table("LOAN_REQUEST")

    op.drop_index("idx_user_user_id", table_name="USER")
    op.drop_table("USER")

    op.drop_index("idx_equipment_category", table_name="EQUIPMENT")
    op.drop_index("idx_equipment_asset_number", table_name="EQUIPMENT")
    op.drop_index("idx_equipment_active_flag", table_name="EQUIPMENT")
    op.drop_table("EQUIPMENT")
