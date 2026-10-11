"""SQLite connection and table setup."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DATABASE_FILE = Path(__file__).resolve().parent.parent / "projects.db"


@contextmanager
def database_connection() -> Iterator[sqlite3.Connection]:
    """Open a database connection and always close it after the operation."""

    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    # SQLite does not enforce foreign keys unless this is turned on per connection.
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    """Create the projects and tasks tables the first time the app runs."""

    with database_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'planning'
                    CHECK (status IN ('planning', 'active', 'on_hold', 'completed'))
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'todo'
                    CHECK (status IN ('todo', 'in_progress', 'done')),
                priority TEXT NOT NULL DEFAULT 'medium'
                    CHECK (priority IN ('low', 'medium', 'high')),
                due_date TEXT,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            )
            """
        )
