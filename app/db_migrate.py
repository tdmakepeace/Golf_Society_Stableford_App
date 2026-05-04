"""
SQLite schema upgrades for existing installs (pre–three-tier).
Safe to run repeatedly.
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from . import db


def _cols(table: str) -> set[str]:
    try:
        insp = inspect(db.engine)
        if not insp.has_table(table):
            return set()
        return {c["name"] for c in insp.get_columns(table)}
    except Exception:
        return set()


def run_sqlite_legacy_migrations() -> None:
    if not db.engine.url.drivername.startswith("sqlite"):
        return

    insp = inspect(db.engine)
    if not insp.has_table("admins"):
        return

    with db.engine.begin() as conn:
        if not insp.has_table("societies"):
            conn.execute(
                text(
                    "CREATE TABLE societies ("
                    "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
                    "name VARCHAR(200) NOT NULL)"
                )
            )

        cols_admins = _cols("admins")
        if "society_id" not in cols_admins:
            conn.execute(
                text(
                    "ALTER TABLE admins ADD COLUMN society_id INTEGER "
                    "REFERENCES societies(id)"
                )
            )
            n_soc = conn.execute(text("SELECT COUNT(*) FROM societies")).scalar() or 0
            if n_soc == 0:
                conn.execute(
                    text("INSERT INTO societies (name) VALUES ('Migrated society')")
                )
            sid = conn.execute(
                text("SELECT id FROM societies ORDER BY id ASC LIMIT 1")
            ).scalar()
            if sid is not None:
                conn.execute(
                    text(
                        "UPDATE admins SET society_id = :sid WHERE society_id IS NULL"
                    ),
                    {"sid": sid},
                )

        if insp.has_table("courses"):
            cols_c = _cols("courses")
            if "society_id" not in cols_c:
                conn.execute(
                    text(
                        "ALTER TABLE courses ADD COLUMN society_id INTEGER "
                        "REFERENCES societies(id)"
                    )
                )
            if "postcode" not in cols_c:
                conn.execute(
                    text(
                        "ALTER TABLE courses ADD COLUMN postcode VARCHAR(32) DEFAULT ''"
                    )
                )
            if "created_by_admin_id" not in cols_c:
                conn.execute(
                    text(
                        "ALTER TABLE courses ADD COLUMN created_by_admin_id INTEGER "
                        "REFERENCES admins(id)"
                    )
                )

            cols_c2 = _cols("courses")
            if "admin_id" in cols_c2:
                conn.execute(
                    text(
                        "UPDATE courses SET created_by_admin_id = admin_id "
                        "WHERE created_by_admin_id IS NULL AND admin_id IS NOT NULL"
                    )
                )
                conn.execute(
                    text(
                        "UPDATE courses SET society_id = ("
                        "SELECT society_id FROM admins WHERE admins.id = courses.admin_id"
                        ") WHERE society_id IS NULL AND admin_id IS NOT NULL"
                    )
                )

            conn.execute(
                text(
                    "UPDATE courses SET society_id = (SELECT id FROM societies ORDER BY id ASC LIMIT 1) "
                    "WHERE society_id IS NULL"
                )
            )
            conn.execute(
                text(
                    "UPDATE courses SET created_by_admin_id = ("
                    "SELECT id FROM admins ORDER BY id ASC LIMIT 1) "
                    "WHERE created_by_admin_id IS NULL"
                )
            )

        if insp.has_table("competitions"):
            cols_comp = _cols("competitions")
            if "password_hash" not in cols_comp:
                conn.execute(
                    text(
                        "ALTER TABLE competitions ADD COLUMN password_hash VARCHAR(256)"
                    )
                )
            if "locked" not in cols_comp:
                conn.execute(
                    text(
                        "ALTER TABLE competitions ADD COLUMN locked INTEGER NOT NULL DEFAULT 0"
                    )
                )

        if insp.has_table("societies"):
            cols_soc = _cols("societies")
            if "locked" not in cols_soc:
                conn.execute(
                    text(
                        "ALTER TABLE societies ADD COLUMN locked INTEGER NOT NULL DEFAULT 0"
                    )
                )
