"""add_api_tables

Revision ID: b8c4d6e78901
Revises: a7b3f9e12345
Create Date: 2026-03-08 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b8c4d6e78901"
down_revision: Union[str, Sequence[str], None] = "a7b3f9e12345"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add API-related tables: crawl_runs and api_keys."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "crawl_runs" not in inspector.get_table_names():
        op.create_table(
            "crawl_runs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("project", sa.String(255), nullable=False, server_default="default"),
            sa.Column("spider_id", sa.Integer(), nullable=False),
            sa.Column("trigger_source", sa.String(50), nullable=False, server_default="cli"),
            sa.Column("trigger_actor", sa.String(255), nullable=True),
            sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
            sa.Column("requested_limit", sa.Integer(), nullable=True),
            sa.Column("output_mode", sa.String(50), nullable=False, server_default="db"),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("items_scraped", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["spider_id"],
                ["spiders.id"],
            ),
            sa.PrimaryKeyConstraint(["id"]),
        )
        op.create_index(op.f("ix_crawl_runs_id"), "crawl_runs", ["id"], unique=False)

    if "api_keys" not in inspector.get_table_names():
        op.create_table(
            "api_keys",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("key_hash", sa.String(64), nullable=False),
            sa.Column("project", sa.String(255), nullable=True),
            sa.Column("scopes", sa.JSON(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_by", sa.String(50), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint(["id"]),
        )
        op.create_index(op.f("ix_api_keys_id"), "api_keys", ["id"], unique=False)
        op.create_index(op.f("ix_api_keys_key_hash"), "api_keys", ["key_hash"], unique=True)


def downgrade() -> None:
    """Remove API-related tables."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "api_keys" in inspector.get_table_names():
        op.drop_index(op.f("ix_api_keys_key_hash"), table_name="api_keys")
        op.drop_index(op.f("ix_api_keys_id"), table_name="api_keys")
        op.drop_table("api_keys")

    if "crawl_runs" in inspector.get_table_names():
        op.drop_index(op.f("ix_crawl_runs_id"), table_name="crawl_runs")
        op.drop_table("crawl_runs")
