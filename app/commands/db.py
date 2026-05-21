import os

import click
from sqlalchemy import create_engine, text

from app.database import init_db


def _try_connect():
    """Attempt a real connection and return (ok, error_message, url)."""
    url = os.getenv("DATABASE_URL")
    if not url:
        return False, "DATABASE_URL is not set in .env.", None
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None, url
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", url


@click.group()
def db():
    """Manage the database."""
    pass


@db.command()
def init():
    """Create all tables defined in app/models.py."""
    ok, err, url = _try_connect()
    if not ok:
        raise click.ClickException(
            f"Database not reachable ({url}): {err}\n"
            "Check DATABASE_URL and that the DB is up "
            "(e.g. `docker compose up -d postgres`)."
        )
    if init_db():
        click.echo("Database schema created.")
    else:
        raise click.ClickException("Failed to initialize database schema.")


@db.command()
def check():
    """Check database connectivity."""
    ok, err, url = _try_connect()
    if ok:
        click.echo(f"Database is reachable at {url}.")
    else:
        raise click.ClickException(
            f"Database not reachable at {url}: {err}"
        )
