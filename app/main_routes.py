from __future__ import annotations

from flask import Blueprint, redirect, render_template, session, url_for
from flask_login import current_user, logout_user

from .models import Admin, SuperAdmin, User
from .user_routes import PLAYER_COMPETITION_IDS

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        if isinstance(current_user, SuperAdmin):
            return redirect(url_for("super_admin.dashboard"))
        if isinstance(current_user, Admin):
            return redirect(url_for("admin.dashboard"))
        if isinstance(current_user, User):
            if session.get(PLAYER_COMPETITION_IDS):
                return redirect(url_for("user.dashboard"))
            session.pop(PLAYER_COMPETITION_IDS, None)
            logout_user()
    return render_template("index.html")


@bp.route("/about")
def about():
    return render_template("about.html")
