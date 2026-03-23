"""add_webhook_tables

Revision ID: c9d5e7f89012
Reveses: b8c4d6e78901
Create Date: 2026-03-08 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c9d5e7f89012"
down_revision: Union[str, Sequence[str], None] = "b8c4d6e78901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add webhook subscription and delivery tables."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "webhook_subscriptions" not in inspector.get_table_names():
        op.create_table(
            "webhook_subscriptions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("project", sa.String(255), nullable=False),
            sa.Column("target_url", sa.String(500), nullable=False),
            sa.Column("event_types", sa.JSON(), nullable=False),
            sa.Column("secret", sa.String(255), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint(["id"]),
        )
        op.create_index(
            op.f("ix_webhook_subscriptions_id"), "webhook_subscriptions", ["id"], unique=False
        )

    if "webhook_deliveries" not in inspector.get_table_names():
        op.create_table(
            "webhook_deliveries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("subscription_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(100), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
            sa.Column("attempt", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("delivered_at", sa.DateTime(), nullable=True),
            sa.Column("response_status", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["subscription_id"],
                ["webhook_subscriptions.id"],
            ),
            sa.PrimaryKeyConstraint(["id"]),
        )
        op.create_index(
            op.f("ix_webhook_deliveries_id"), "webhook_deliveries", ["id"], unique=False
        )


def downgrade() -> None:
    """Remove webhook tables."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "webhook_deliveries" in inspector.get_table_names():
        op.drop_index(op.f("ix_webhook_deliveries_id"), table_name="webhook_deliveries")
        op.drop_table("webhook_deliveries")

    if "webhook_subscriptions" in inspector.get_table_names():
        op.drop_index(op.f("ix_webhook_subscriptions_id"), table_name="webhook_subscriptions")
        op.drop_table("webhook_subscriptions")
