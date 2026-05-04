from __future__ import annotations

import os
import time

import click
from flask import Flask, flash, redirect, request, session, url_for
from flask_login import LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _ensure_bootstrap_super_admin(app: Flask, db: SQLAlchemy) -> None:
    """
    If there is no super admin (e.g. fresh SQLite), create one.
    Override BOOTSTRAP_SUPER_ADMIN_EMAIL / BOOTSTRAP_SUPER_ADMIN_PASSWORD.
    """
    from .models import SuperAdmin
    from .validators import validate_email_address, validate_password

    if SuperAdmin.query.count() > 0:
        return

    email = os.environ.get("BOOTSTRAP_SUPER_ADMIN_EMAIL", "superadmin@example.com")
    password = os.environ.get("BOOTSTRAP_SUPER_ADMIN_PASSWORD", "GolfSuper1!")
    try:
        em = validate_email_address(email)
        validate_password(password)
    except ValueError as exc:
        app.logger.error("Bootstrap super admin skipped: invalid env: %s", exc)
        return

    sa = SuperAdmin(email=em)
    sa.set_password(password)
    db.session.add(sa)
    db.session.commit()
    app.logger.warning(
        "No super admins; created %s. Change password in production.", em
    )


db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()
login_manager.login_view = "main.index"
login_manager.login_message_category = "info"

SESSION_LAST_ACTIVITY_KEY = "_session_last_activity"
SESSION_IDLE_SECONDS = 600  # 10 minutes


@login_manager.unauthorized_handler
def _unauthorized():
    if request.blueprint == "super_admin":
        return redirect(url_for("super_admin.login", next=request.url))
    if request.blueprint == "admin":
        return redirect(url_for("admin.login", next=request.url))
    return redirect(url_for("user.login", next=request.url))


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me-in-production"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL",
            "sqlite:///" + os.path.join(app.instance_path, "golfsociety.sqlite"),
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    if test_config:
        app.config.update(test_config)

    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    db.init_app(app)
    login_manager.init_app(app)

    from . import models  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id: str):
        from .models import Admin, SuperAdmin, User

        if user_id.startswith("sa:"):
            return db.session.get(SuperAdmin, int(user_id[3:]))
        if user_id.startswith("a:"):
            return db.session.get(Admin, int(user_id[2:]))
        if user_id.startswith("u:"):
            return db.session.get(User, int(user_id[2:]))
        return None

    from . import admin_routes, main_routes, super_admin_routes, user_routes

    app.register_blueprint(main_routes.bp)
    app.register_blueprint(super_admin_routes.bp)
    app.register_blueprint(admin_routes.bp)
    app.register_blueprint(user_routes.bp)

    @app.before_request
    def _enforce_session_idle_timeout():
        if request.endpoint == "static":
            return None
        if not current_user.is_authenticated:
            session.pop(SESSION_LAST_ACTIVITY_KEY, None)
            return None
        now = time.time()
        last = session.get(SESSION_LAST_ACTIVITY_KEY)
        if last is not None and (now - float(last)) > SESSION_IDLE_SECONDS:
            session.pop(SESSION_LAST_ACTIVITY_KEY, None)
            from .models import User

            if isinstance(current_user, User):
                session.pop(user_routes.PLAYER_COMPETITION_IDS, None)
            logout_user()
            flash("You were signed out after 10 minutes of inactivity.", "info")
            bp = request.blueprint
            if bp == "super_admin":
                return redirect(url_for("super_admin.login"))
            if bp == "admin":
                return redirect(url_for("admin.login"))
            if bp == "user":
                return redirect(url_for("user.login"))
            return redirect(url_for("main.index"))
        session[SESSION_LAST_ACTIVITY_KEY] = now
        return None

    @app.cli.command("create-society-admin")
    @click.argument("email")
    @click.argument("password")
    @click.argument("society_id", type=int)
    def create_society_admin_command(email: str, password: str, society_id: int) -> None:
        """Add a society admin to an existing society by id."""
        from .models import Admin, Society
        from .validators import validate_email_address, validate_password

        em = validate_email_address(email)
        validate_password(password)
        soc = db.session.get(Society, society_id)
        if not soc:
            click.echo("Society id not found.")
            raise SystemExit(1)
        if soc.locked:
            click.echo("That society is locked; unlock it in super admin first.")
            raise SystemExit(1)
        if Admin.query.filter_by(email=em).first():
            click.echo("An admin with that email already exists.")
            raise SystemExit(1)
        admin = Admin(email=em, society_id=society_id)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo("Society admin created.")

    with app.app_context():
        db.create_all()
        if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:"):
            from .db_migrate import run_sqlite_legacy_migrations

            run_sqlite_legacy_migrations()
        _ensure_bootstrap_super_admin(app, db)

    return app
