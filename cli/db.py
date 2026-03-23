import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import click

from utils.secret_redaction import redact_url_credentials as redact_url_credentials

# Whitelist of valid table names (prevents SQL injection)
VALID_TABLES = {
    "spiders",
    "scraped_items",
    "crawl_queue",
    "spider_rules",
    "spider_settings",
    "crawl_runs",
    "api_keys",
    "webhook_subscriptions",
    "webhook_deliveries",
    "alembic_version",
}


def validate_table_name(table_name):
    """Validate table name against whitelist.

    Raises:
        ValueError: If table name is not in whitelist
    """
    if table_name not in VALID_TABLES:
        valid_list = ", ".join(sorted(VALID_TABLES))
        raise ValueError(f"Invalid table name: '{table_name}'\nValid tables: {valid_list}")


def is_postgresql():
    """Check if database is PostgreSQL"""
    from core.db import engine

    return "postgresql" in str(engine.url)


def is_sqlite():
    """Check if database is SQLite"""
    from core.db import engine

    return "sqlite" in str(engine.url)


def _get_alembic_command():
    """Resolve the Alembic executable for the current Python environment."""
    python_path = Path(sys.executable)
    candidates = [
        python_path.with_name("alembic"),
        python_path.with_name("alembic.exe"),
    ]

    for candidate in candidates:
        if candidate.exists():
            return [str(candidate)]

    fallback = shutil.which("alembic")
    if fallback:
        return [fallback]

    raise FileNotFoundError(
        "Alembic executable not found. Run 'python scrapai setup' or install requirements."
    )


@click.group()
def db():
    """Database management"""
    pass


@db.command("migrate")
def migrate():
    """Run database migrations"""
    click.echo("Running database migrations...")
    try:
        result = subprocess.run(
            _get_alembic_command() + ["upgrade", "head"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if result.returncode == 0:
            click.echo("Migrations completed successfully.")
        else:
            click.echo("Migration failed.")
    except Exception as e:
        click.echo(f"Error running migrations: {e}")


@db.command("current")
def current():
    """Show current migration revision"""
    try:
        subprocess.run(
            _get_alembic_command() + ["current"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
    except Exception as e:
        click.echo(f"Error checking current revision: {e}")


@db.command("stats")
def stats():
    """Show database statistics (counts of spiders, items, queue)"""
    from sqlalchemy import text

    from core.db import get_db

    try:
        db = next(get_db())

        # Get counts
        spider_count = db.execute(text("SELECT COUNT(*) FROM spiders")).scalar()
        item_count = db.execute(text("SELECT COUNT(*) FROM scraped_items")).scalar()
        project_count = db.execute(
            text("SELECT COUNT(DISTINCT project) FROM spiders WHERE project IS NOT NULL")
        ).scalar()

        # Queue breakdown
        queue_total = db.execute(text("SELECT COUNT(*) FROM crawl_queue")).scalar()
        queue_pending = db.execute(
            text("SELECT COUNT(*) FROM crawl_queue WHERE status = 'pending'")
        ).scalar()
        queue_processing = db.execute(
            text("SELECT COUNT(*) FROM crawl_queue WHERE status = 'processing'")
        ).scalar()
        queue_completed = db.execute(
            text("SELECT COUNT(*) FROM crawl_queue WHERE status = 'completed'")
        ).scalar()
        queue_failed = db.execute(
            text("SELECT COUNT(*) FROM crawl_queue WHERE status = 'failed'")
        ).scalar()
        spider_count = int(spider_count or 0)
        item_count = int(item_count or 0)
        project_count = int(project_count or 0)
        queue_total = int(queue_total or 0)
        queue_pending = int(queue_pending or 0)
        queue_processing = int(queue_processing or 0)
        queue_completed = int(queue_completed or 0)
        queue_failed = int(queue_failed or 0)

        click.echo("Database Statistics\n")
        click.echo(f"   Spiders: {spider_count:,}")
        click.echo(f"   Scraped Items: {item_count:,}")
        click.echo(f"   Projects: {project_count:,}")
        click.echo(f"\n   Queue Items: {queue_total:,}")
        if queue_total > 0:
            click.echo(f"      - Pending: {queue_pending:,}")
            click.echo(f"      - Processing: {queue_processing:,}")
            click.echo(f"      - Completed: {queue_completed:,}")
            click.echo(f"      - Failed: {queue_failed:,}")

    except Exception as e:
        click.echo(f"Error: failed to get statistics: {e}")


@db.command("tables")
def tables():
    """List all tables with row counts"""
    from sqlalchemy import text

    from core.db import get_db

    try:
        db = next(get_db())

        # Get table names (works for both SQLite and PostgreSQL)
        if is_postgresql():
            result = db.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
        else:  # SQLite
            result = db.execute(text("""
                SELECT name as table_name
                FROM sqlite_master
                WHERE type='table'
                ORDER BY name
            """))

        table_names = [row[0] for row in result]

        if not table_names:
            click.echo("(no tables found)")
            return

        click.echo("Database Tables\n")

        # Get row count for each table
        max_name_len = max(len(name) for name in table_names)

        for table_name in table_names:
            try:
                # Validate table name before using in SQL
                validate_table_name(table_name)
                count = db.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")  # nosec B608
                ).scalar()
                click.echo(f"   {table_name.ljust(max_name_len)}  {count:,} rows")
            except ValueError:
                # Invalid table name - skip it
                click.echo(f"   {table_name.ljust(max_name_len)}  (skipped: not a ScrapAI table)")
            except Exception as e:
                click.echo(f"   {table_name.ljust(max_name_len)}  (error: {e})")

    except Exception as e:
        click.echo(f"Error: failed to list tables: {e}")


@db.command("inspect")
@click.argument("table")
def inspect(table):
    """Show schema for a specific table

    Example: ./scrapai db inspect spiders
    """
    from core.db import get_db

    # Validate table name before using in SQL
    try:
        validate_table_name(table)
    except ValueError as e:
        click.echo(f"Error: {e}")
        return

    try:
        db = next(get_db())
        from sqlalchemy import text

        click.echo(f"Table: {table}\n")

        # Get schema (works for both SQLite and PostgreSQL)
        # Note: table name already validated against whitelist above
        if is_postgresql():
            result = db.execute(
                text("""
                SELECT
                    column_name,
                    data_type,
                    character_maximum_length,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_name = :table_name
                ORDER BY ordinal_position
            """),
                {"table_name": table},
            )

            click.echo("Column                Type                 Nullable  Default")
            click.echo("-" * 70)

            for row in result:
                col_name = row[0]
                data_type = row[1]
                max_len = row[2]
                nullable = row[3]
                default = row[4]

                if max_len:
                    type_str = f"{data_type}({max_len})"
                else:
                    type_str = data_type

                null_str = "YES" if nullable == "YES" else "NO"
                default_str = str(default) if default else ""

                click.echo(f"{col_name:20}  {type_str:18}  {null_str:8}  {default_str}")

        else:  # SQLite
            # Note: table name already validated against whitelist above
            result = db.execute(text(f"PRAGMA table_info({table})"))

            click.echo("Column                Type                 Nullable  Default")
            click.echo("-" * 70)

            for row in result:
                col_name = row[1]
                data_type = row[2]
                not_null = row[3]
                default = row[4]

                null_str = "NO" if not_null else "YES"
                default_str = str(default) if default else ""

                click.echo(f"{col_name:20}  {data_type:18}  {null_str:8}  {default_str}")

        # Show row count
        # Note: table name already validated against whitelist above
        count = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()  # nosec B608
        click.echo(f"\nTotal rows: {count:,}")

    except Exception as e:
        click.echo(f"Error: failed to inspect table '{table}': {e}")


def _build_count_query(sql):
    """Build a SELECT COUNT(*) query from an UPDATE or DELETE statement.

    Extracts the table and WHERE clause to preview affected rows.
    Returns the count SQL string, or None if parsing fails.
    """
    sql_stripped = sql.strip().rstrip(";")

    # UPDATE <table> SET ... [WHERE ...]
    update_match = re.match(
        r"UPDATE\s+(\w+)\s+SET\s+.+?(WHERE\s+.+)?$",
        sql_stripped,
        re.IGNORECASE | re.DOTALL,
    )
    if update_match:
        table = update_match.group(1)
        where = update_match.group(2) or ""
        return f"SELECT COUNT(*) FROM {table} {where}".strip()  # nosec B608

    # DELETE FROM <table> [WHERE ...]
    delete_match = re.match(
        r"DELETE\s+FROM\s+(\w+)(\s+WHERE\s+.+)?$",
        sql_stripped,
        re.IGNORECASE | re.DOTALL,
    )
    if delete_match:
        table = delete_match.group(1)
        where = delete_match.group(2) or ""
        return f"SELECT COUNT(*) FROM {table} {where}".strip()  # nosec B608

    return None


def _format_results(rows, result, format, json_lib):
    """Format and display query results."""
    if not rows:
        click.echo("(no results)")
        return

    if format == "json":
        columns = result.keys()
        output = [dict(zip(columns, row)) for row in rows]
        click.echo(json_lib.dumps(output, indent=2, default=str))

    elif format == "csv":
        columns = result.keys()
        click.echo(",".join(columns))
        for row in rows:
            click.echo(",".join(str(v) for v in row))

    else:  # table format (default)
        columns = result.keys()

        # Calculate column widths
        col_widths = [len(str(col)) for col in columns]
        for row in rows:
            for i, val in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(val)))

        # Print header
        header = " | ".join(str(col).ljust(width) for col, width in zip(columns, col_widths))
        click.echo(header)
        click.echo("-" * len(header))

        # Print rows
        for row in rows:
            click.echo(" | ".join(str(val).ljust(width) for val, width in zip(row, col_widths)))

        click.echo(f"\n({len(rows)} rows)")


@db.command("query")
@click.argument("sql")
@click.option(
    "--format",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt for UPDATE/DELETE",
)
def query(sql, format, yes):
    """Execute a SQL query against the database.

    SELECT, UPDATE, and DELETE queries are allowed.
    UPDATE and DELETE show affected row count and require confirmation.

    Examples:
      ./scrapai db query "SELECT * FROM spiders LIMIT 5"
      ./scrapai db query "UPDATE spider_settings SET value='3' WHERE key='DOWNLOAD_DELAY'"
      ./scrapai db query "DELETE FROM scraped_items WHERE spider_id = 5"
      ./scrapai db query "SELECT COUNT(*) FROM scraped_items" --format json
    """
    import json as json_lib

    from core.db import get_db

    # Safety check - only allow SELECT, UPDATE, DELETE
    sql_upper = sql.strip().upper()
    allowed_prefixes = ("SELECT", "UPDATE", "DELETE")
    if not any(sql_upper.startswith(prefix) for prefix in allowed_prefixes):
        click.echo("Error: only SELECT, UPDATE, and DELETE queries are allowed")
        click.echo("   INSERT, DROP, ALTER, and TRUNCATE are blocked for safety")
        return

    is_write = not sql_upper.startswith("SELECT")

    try:
        db = next(get_db())
        from sqlalchemy import text

        if is_write:
            # Preview affected rows before executing
            count_sql = _build_count_query(sql)
            if count_sql:
                try:
                    affected = db.execute(text(count_sql)).scalar()
                except Exception:
                    affected = "unknown"
            else:
                affected = "unknown"

            op = "UPDATE" if sql_upper.startswith("UPDATE") else "DELETE"

            if not yes:
                click.echo(
                    f"Warning: this will {op} {affected} row(s). Continue? [y/N] ",
                    nl=False,
                )
                confirm = click.getchar()
                click.echo()  # newline after input
                if confirm.lower() != "y":
                    click.echo("Cancelled.")
                    return

            result = db.execute(text(sql))
            db.commit()
            rowcount_value = getattr(result, "rowcount", None)
            rowcount = "unknown" if rowcount_value is None else str(rowcount_value)
            click.echo(f"{op} complete - {rowcount} row(s) affected")

        else:
            result = db.execute(text(sql))
            rows = result.fetchall()
            _format_results(rows, result, format, json_lib)

    except Exception as e:
        click.echo(f"Error: query failed: {e}")


@db.command("transfer")
@click.argument("source_url")
@click.option(
    "--skip-items",
    is_flag=True,
    help="Skip scraped_items (transfer only spiders and queue)",
)
def transfer(source_url, skip_items):
    """Transfer data from another database into the current one.

    First update DATABASE_URL in .env to your new database, then run:

    \b
      ./scrapai db transfer sqlite:///scrapai.db
      ./scrapai db transfer postgresql://old-host/dbname

    SOURCE_URL is the old database to copy FROM. Data is written to
    whatever DATABASE_URL is currently set in .env.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from core.db import DATABASE_URL, Base, SessionLocal
    from core.models import CrawlQueue, ScrapedItem, Spider, SpiderRule, SpiderSetting

    if source_url == DATABASE_URL:
        click.echo("Error: source is the same as current database.")
        click.echo("   Update DATABASE_URL in .env to your new database first.")
        return

    # Redact credentials before printing
    redacted_source = redact_url_credentials(source_url)
    redacted_target = redact_url_credentials(DATABASE_URL)

    click.echo(f"Source (old): {redacted_source}")
    click.echo(f"Target (current): {redacted_target}")

    # Connect to source
    source_engine = create_engine(source_url)
    SourceSession = sessionmaker(bind=source_engine)

    # Ensure target tables exist
    Base.metadata.create_all(bind=SessionLocal().get_bind())

    source = SourceSession()
    target = SessionLocal()

    try:
        # Transfer spiders with rules and settings
        spiders = source.query(Spider).all()
        click.echo(f"\nTransferring {len(spiders)} spiders...")

        spider_id_map = {}
        for s in spiders:
            new_spider = Spider(
                name=s.name,
                allowed_domains=s.allowed_domains,
                start_urls=s.start_urls,
                source_url=s.source_url,
                active=s.active,
                project=s.project,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            target.add(new_spider)
            target.flush()
            spider_id_map[s.id] = new_spider.id

            for r in s.rules:
                target.add(
                    SpiderRule(
                        spider_id=new_spider.id,
                        allow_patterns=r.allow_patterns,
                        deny_patterns=r.deny_patterns,
                        restrict_xpaths=r.restrict_xpaths,
                        restrict_css=r.restrict_css,
                        callback=r.callback,
                        follow=r.follow,
                        priority=r.priority,
                    )
                )

            for st in s.settings:
                target.add(
                    SpiderSetting(
                        spider_id=new_spider.id,
                        key=st.key,
                        value=st.value,
                        type=st.type,
                    )
                )

        click.echo(f"   OK: {len(spiders)} spiders (with rules and settings)")

        # Transfer scraped items
        if not skip_items:
            item_count = source.query(ScrapedItem).count()
            click.echo(f"\nTransferring {item_count} scraped items...")

            batch_size = 1000
            transferred = 0
            for spider_id_old, spider_id_new in spider_id_map.items():
                items = (
                    source.query(ScrapedItem).filter(ScrapedItem.spider_id == spider_id_old).all()
                )
                for item in items:
                    target.add(
                        ScrapedItem(
                            spider_id=spider_id_new,
                            url=item.url,
                            title=item.title,
                            content=item.content,
                            published_date=item.published_date,
                            author=item.author,
                            scraped_at=item.scraped_at,
                            metadata_json=item.metadata_json,
                        )
                    )
                    transferred += 1
                    if transferred % batch_size == 0:
                        target.flush()
                        click.echo(f"   ... {transferred}/{item_count}")

            click.echo(f"   OK: {transferred} items")
        else:
            click.echo("\nSkipping scraped items (--skip-items)")

        # Transfer queue
        queue_items = source.query(CrawlQueue).all()
        click.echo(f"\nTransferring {len(queue_items)} queue items...")

        for q in queue_items:
            target.add(
                CrawlQueue(
                    project_name=q.project_name,
                    website_url=q.website_url,
                    custom_instruction=q.custom_instruction,
                    status=q.status,
                    priority=q.priority,
                    error_message=q.error_message,
                    retry_count=q.retry_count,
                    created_at=q.created_at,
                    updated_at=q.updated_at,
                    completed_at=q.completed_at,
                )
            )

        click.echo(f"   OK: {len(queue_items)} queue items")

        target.commit()
        click.echo("\nTransfer complete. Your new database is ready.")

    except Exception as e:
        target.rollback()
        click.echo(f"\nError: transfer failed: {e}")
        raise
    finally:
        source.close()
        target.close()
        source_engine.dispose()
