"""add_crawl_run_id_to_scraped_items

Revision ID: abc12345ef78901
Revises: c9d5e7f89012
Create Date: 2026-03-08 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "abc12345ef78901"
down_revision: Union[str, Sequence[str], None] = "c9d5e7f89012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_column_names(inspector: sa.Inspector, table_name: str) -> list[str]:
    return [column["name"] for column in inspector.get_columns(table_name)]


def _get_index_names(inspector: sa.Inspector, table_name: str) -> list[str]:
    return [index["name"] for index in inspector.get_indexes(table_name)]


def _get_foreign_key_names(inspector: sa.Inspector, table_name: str) -> list[str]:
    names = []
    for foreign_key in inspector.get_foreign_keys(table_name):
        name = foreign_key.get("name")
        if name:
            names.append(name)
    return names


def upgrade() -> None:
    """Add crawl_run_id to scraped_items with index and foreign key."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "scraped_items" not in inspector.get_table_names():
        return

    if "crawl_run_id" not in _get_column_names(inspector, "scraped_items"):
        with op.batch_alter_table("scraped_items") as batch_op:
            batch_op.add_column(sa.Column("crawl_run_id", sa.Integer(), nullable=True))

    inspector = sa.inspect(conn)
    index_names = _get_index_names(inspector, "scraped_items")
    if op.f("ix_scraped_items_crawl_run_id") not in index_names:
        op.create_index(
            op.f("ix_scraped_items_crawl_run_id"),
            "scraped_items",
            ["crawl_run_id"],
            unique=False,
        )

    if conn.dialect.name != "sqlite":
        inspector = sa.inspect(conn)
        foreign_key_name = "fk_scraped_items_crawl_run_id_crawl_runs"
        if foreign_key_name not in _get_foreign_key_names(inspector, "scraped_items"):
            with op.batch_alter_table("scraped_items") as batch_op:
                batch_op.create_foreign_key(
                    foreign_key_name,
                    "crawl_runs",
                    ["crawl_run_id"],
                    ["id"],
                )


def downgrade() -> None:
    """Remove crawl_run_id from scraped_items."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "scraped_items" not in inspector.get_table_names():
        return

    if conn.dialect.name != "sqlite":
        foreign_key_name = "fk_scraped_items_crawl_run_id_crawl_runs"
        if foreign_key_name in _get_foreign_key_names(inspector, "scraped_items"):
            with op.batch_alter_table("scraped_items") as batch_op:
                batch_op.drop_constraint(foreign_key_name, type_="foreignkey")

    inspector = sa.inspect(conn)
    index_names = _get_index_names(inspector, "scraped_items")
    if op.f("ix_scraped_items_crawl_run_id") in index_names:
        op.drop_index(op.f("ix_scraped_items_crawl_run_id"), table_name="scraped_items")

    inspector = sa.inspect(conn)
    if "crawl_run_id" in _get_column_names(inspector, "scraped_items"):
        with op.batch_alter_table("scraped_items") as batch_op:
            batch_op.drop_column("crawl_run_id")
