from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

from .models import Admin, SuperAdmin, User

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        if isinstance(current_user, SuperAdmin):
            return redirect(url_for("super_admin.dashboard"))
        if isinstance(current_user, Admin):
            return redirect(url_for("admin.dashboard"))
        if isinstance(current_user, User):
            return redirect(url_for("user.dashboard"))
    return render_template("index.html")


@bp.route("/about")
def about():
    return render_template("about.html")
