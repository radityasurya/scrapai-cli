import asyncio
import sys

import click


@click.group()
def spiders():
    """Spider management"""
    pass


@spiders.command("list")
@click.option("--project", default=None, help="Filter by project name (default: show all)")
def list_spiders(project):
    """List all spiders in DB"""
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())

    query = db.query(Spider)
    if project:
        query = query.filter(Spider.project == project)
        click.echo(f"📋 Available Spiders (DB) - Project: {project}:")
    else:
        click.echo("📋 Available Spiders (DB) - All Projects:")

    spiders = query.all()
    if spiders:
        for s in spiders:
            created = s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "Unknown"
            updated = s.updated_at.strftime("%Y-%m-%d %H:%M") if s.updated_at else created
            project_tag = f"[{s.project}]" if s.project else "[default]"

            click.echo(
                f"  • {s.name} {project_tag} (Active: {s.active}) - "
                f"Created: {created}, Updated: {updated}"
            )
            if s.source_url:
                click.echo(f"    Source: {s.source_url}")
    else:
        if project:
            click.echo(f"No spiders found in project '{project}'.")
        else:
            click.echo("No spiders found in database.")


@spiders.command("import")
@click.argument("file")
@click.option("--project", default="default", help="Project name (default: default)")
@click.option(
    "--skip-validation",
    is_flag=True,
    help="Skip Pydantic validation (backward compatibility)",
)
def import_spider(file, project, skip_validation):
    """Import spider from JSON file (use "-" for stdin)"""
    from core.db import get_db
    from services.spider_import_service import SpiderImportService

    db = next(get_db())
    service = SpiderImportService()

    if skip_validation:
        click.echo("⚠️  Skipping validation (--skip-validation flag)")

    stdin_data = sys.stdin.read() if file == "-" else None
    result = asyncio.run(
        service.import_spider(
            db=db,
            file_path=file,
            project=project,
            skip_validation=skip_validation,
            stdin_data=stdin_data,
        )
    )

    if not result["success"]:
        click.echo(f"❌ {result['error']}")
        return

    if result["action"] == "updated":
        click.echo(f"⚠️  Spider '{result['spider_name']}' already exists. Updating...")

    click.echo(f"✅ Spider '{result['spider_name']}' imported successfully!")
    click.echo(f"   Project: {result['project']}")
    click.echo(f"   Domains: {', '.join(result['allowed_domains'])}")
    click.echo(f"   Start URLs: {len(result['start_urls'])}")
    click.echo(f"   Rules: {result['rules_count']}")
    if result["callbacks"]:
        click.echo(f"   Callbacks: {len(result['callbacks'])} ({', '.join(result['callbacks'])})")


@spiders.command("delete")
@click.argument("name")
@click.option("--project", default=None, help="Project name")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def delete_spider(name, project, force):
    """Delete a spider"""
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())
    query = db.query(Spider).filter(Spider.name == name)

    if project:
        query = query.filter(Spider.project == project)
        project_msg = f" in project '{project}'"
    else:
        project_msg = ""

    spider = query.first()

    if spider:
        if not force:
            confirm = input(
                f"Are you sure you want to delete spider '{name}'{project_msg}? (y/N): "
            )
            if confirm.lower() != "y":
                click.echo("❌ Delete cancelled")
                return

        db.delete(spider)
        db.commit()
        click.echo(f"🗑️  Spider '{name}'{project_msg} deleted!")
    else:
        click.echo(f"❌ Spider '{name}'{project_msg} not found.")
