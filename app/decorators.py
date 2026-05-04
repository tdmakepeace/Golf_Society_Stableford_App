from __future__ import annotations

from functools import wraps

from flask import flash, redirect, request, session, url_for
from flask_login import current_user, logout_user

from . import db
from .models import Admin, Society, SuperAdmin, User


def super_admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not isinstance(current_user, SuperAdmin):
            return redirect(url_for("super_admin.login", next=request.url))
        return f(*args, **kwargs)

    return wrapped


def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not isinstance(current_user, Admin):
            return redirect(url_for("admin.login", next=request.url))
        society = db.session.get(Society, current_user.society_id)
        if society is None or society.locked:
            logout_user()
            flash(
                "This society is locked. Society admins cannot sign in until a super admin unlocks it.",
                "error",
            )
            return redirect(url_for("admin.login"))

        return f(*args, **kwargs)

    return wrapped


def user_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not isinstance(current_user, User):
            return redirect(url_for("user.login", next=request.url))
        if not session.get("player_competition_ids"):
            logout_user()
            return redirect(url_for("user.login", next=request.url))
        return f(*args, **kwargs)

    return wrapped
