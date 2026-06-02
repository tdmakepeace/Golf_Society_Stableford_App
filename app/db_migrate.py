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


def _migrate_courses_global(conn, insp) -> None:
    """Drop society_id so courses are shared app-wide (rebuild table on SQLite)."""
    if not insp.has_table("courses"):
        return
    cols = _cols("courses")
    if "society_id" not in cols:
        return

    conn.execute(
        text(
            "CREATE TABLE courses_global ("
            "id INTEGER NOT NULL PRIMARY KEY, "
            "admin_id INTEGER NOT NULL REFERENCES admins(id), "
            "name VARCHAR(200) NOT NULL, "
            "postcode VARCHAR(32) NOT NULL DEFAULT '')"
        )
    )
    admin_col = "admin_id" if "admin_id" in cols else "created_by_admin_id"
    conn.execute(
        text(
            f"INSERT INTO courses_global (id, admin_id, name, postcode) "
            f"SELECT id, {admin_col}, name, "
            f"COALESCE(postcode, '') FROM courses"
        )
    )
    conn.execute(text("DROP TABLE courses"))
    conn.execute(text("ALTER TABLE courses_global RENAME TO courses"))


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

        _migrate_courses_global(conn, insp)

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
            if "player_password_hash" not in cols_soc:
                conn.execute(
                    text(
                        "ALTER TABLE societies ADD COLUMN player_password_hash VARCHAR(256)"
                    )
                )
            conn.execute(
                text(
                    "UPDATE societies SET player_password_hash = ("
                    "SELECT competitions.password_hash FROM competitions "
                    "JOIN admins ON admins.id = competitions.admin_id "
                    "WHERE admins.society_id = societies.id "
                    "AND competitions.password_hash IS NOT NULL "
                    "ORDER BY competitions.id DESC LIMIT 1"
                    ") WHERE player_password_hash IS NULL"
                )
            )

        if insp.has_table("users"):
            cols_users = _cols("users")
            if "society_id" not in cols_users:
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN society_id INTEGER REFERENCES societies(id)"
                    )
                )
            if "is_deleted" not in cols_users:
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0"
                    )
                )

            cols_users2 = _cols("users")
            if "society_id" in cols_users2:
                conn.execute(
                    text(
                        "UPDATE users SET society_id = ("
                        "SELECT admins.society_id FROM competition_players cp "
                        "JOIN competitions ON competitions.id = cp.competition_id "
                        "JOIN admins ON admins.id = competitions.admin_id "
                        "WHERE cp.user_id = users.id "
                        "ORDER BY cp.competition_id DESC LIMIT 1"
                        ") WHERE society_id IS NULL"
                    )
                )
                conn.execute(
                    text(
                        "UPDATE users SET society_id = (SELECT id FROM societies ORDER BY id ASC LIMIT 1) "
                        "WHERE society_id IS NULL"
                    )
                )
