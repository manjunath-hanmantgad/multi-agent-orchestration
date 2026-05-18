"""Initialize SQLite schema for the enterprise workflow platform."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv

REQUIRED_DATABASE_ENV = "DATABASE_URL"
SQLITE_PREFIX = "sqlite+aiosqlite:///"


def get_database_url() -> str:
    """Load and validate the database URL from environment variables."""
    load_dotenv()
    database_url = os.getenv(REQUIRED_DATABASE_ENV)
    if not database_url:
        raise RuntimeError(f"Missing required environment variable: {REQUIRED_DATABASE_ENV}")
    return database_url


def resolve_sqlite_path(database_url: str) -> Path:
    """Convert a SQLAlchemy SQLite URL into a filesystem path."""
    if not database_url.startswith(SQLITE_PREFIX):
        raise ValueError(
            "scripts/init_db.py supports only sqlite+aiosqlite URLs, "
            f"received: {database_url}"
        )
    raw_path = unquote(database_url[len(SQLITE_PREFIX) :])
    if raw_path == ":memory:":
        raise ValueError("scripts/init_db.py does not support in-memory database URLs")
    return Path(raw_path).expanduser().resolve()


def create_tables(connection: sqlite3.Connection) -> None:
    """Create all required tables if they do not already exist."""
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id TEXT PRIMARY KEY,
            workflow_type TEXT NOT NULL,
            status TEXT NOT NULL,
            current_stage TEXT,
            payload TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            stage TEXT NOT NULL,
            actor TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT,
            FOREIGN KEY (workflow_id) REFERENCES workflow_runs (id)
        );
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_records (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            vendor_name TEXT NOT NULL,
            decision TEXT NOT NULL,
            decision_by TEXT,
            decided_at TEXT,
            notes TEXT,
            FOREIGN KEY (workflow_id) REFERENCES workflow_runs (id)
        );
        """
    )
    connection.commit()


def initialize_database() -> Path:
    """Initialize the SQLite database and return its path."""
    database_path = resolve_sqlite_path(get_database_url())
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        create_tables(connection)
    return database_path


if __name__ == "__main__":
    path = initialize_database()
    print(f"Database initialized at: {path}")
