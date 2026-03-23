import re
from pathlib import Path

import click

from apps.web_api.services.auth_service import AuthService
from core.config import DATA_DIR
from core.db import SessionLocal


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    slug = slug.strip("-.")
    return slug or "default"


def _mask_key(key: str) -> str:
    if len(key) <= 12:
        return "[hidden]"
    return f"{key[:6]}...{key[-4:]}"


def _write_api_key_record(
    key: str,
    name: str,
    project: str | None,
    scopes: tuple[str, ...],
    key_id: int,
) -> Path:
    project_name = project or "global"
    target_dir = Path(DATA_DIR) / "credentials" / "api-keys" / _slugify(project_name)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / f"{_slugify(name)}.env"
    lines = [
        f"SCRAPAI_API_KEY={key}",
        f"SCRAPAI_API_KEY_NAME={name}",
        f"SCRAPAI_API_KEY_ID={key_id}",
        f"SCRAPAI_API_KEY_PROJECT={project_name}",
        f"SCRAPAI_API_KEY_SCOPES={','.join(scopes)}",
    ]
    target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        target_path.chmod(0o600)
    except OSError:
        pass

    return target_path


@click.group()
def apikey():
    """API key management"""
    pass


@apikey.command("create")
@click.argument("name")
@click.option("--project", default=None, help="Project name")
@click.option(
    "--scope",
    "scopes",
    multiple=True,
    help="Optional scope to attach to the key (repeatable)",
)
@click.option(
    "--document/--no-document",
    default=True,
    help="Write the plaintext key to an ignored local credential file",
)
def create_api_key(name, project, scopes, document):
    """Create a new API key without printing the secret."""
    db = SessionLocal()

    try:
        key, api_key = AuthService().create_api_key(
            db,
            name=name,
            project=project,
            scopes=list(scopes),
        )
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    except Exception as exc:
        click.echo(f"Error: failed to create API key: {exc}", err=True)
        raise SystemExit(1)
    finally:
        db.close()

    key_id = getattr(api_key, "id")
    project_name = project or "global"
    click.echo(f"Created API key '{name}' for project '{project_name}'")
    click.echo(f"   Key ID: {key_id}")
    click.echo(f"   Preview: {_mask_key(key)}")

    if document:
        record_path = _write_api_key_record(key, name, project, scopes, key_id)
        click.echo(f"   Stored at: {record_path}")
        click.echo("   The full key is stored in the local credential file only.")


@apikey.command("list")
@click.option("--project", default=None, help="Filter by project name")
@click.option("--all", "active_only", flag_value=False, default=True, help="Include revoked keys")
def list_api_keys(project, active_only):
    """List API keys without exposing secret material."""
    db = SessionLocal()

    try:
        keys = AuthService().list_keys(db, project=project, active_only=active_only)
        if not keys:
            click.echo("No API keys found.")
            return

        click.echo("ID  Name                 Project      Active  Created")
        click.echo("--  -------------------  -----------  ------  -------------------")
        for item in keys:
            project_name = item.project or "global"
            created_at = item.created_at.isoformat(sep=" ", timespec="seconds")
            active = "yes" if item.__dict__.get("active") else "no"
            click.echo(
                f"{str(item.id).ljust(2)}  {item.name[:19].ljust(19)}  "
                f"{project_name[:11].ljust(11)}  {active.ljust(6)}  {created_at}"
            )
    finally:
        db.close()


@apikey.command("revoke")
@click.argument("key_id", type=int)
@click.option("--project", default=None, help="Project name")
def revoke_api_key(key_id, project):
    """Revoke an existing API key by database ID."""
    db = SessionLocal()

    try:
        revoked = AuthService().revoke_key(db, key_id=key_id, project=project)
        if not revoked:
            click.echo("Error: API key not found or project does not match", err=True)
            raise SystemExit(1)
        click.echo(f"Revoked API key {key_id}")
    finally:
        db.close()
