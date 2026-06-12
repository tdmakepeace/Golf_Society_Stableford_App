from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from . import db
from .decorators import super_admin_required
from .models import Admin, Society, SuperAdmin
from .validators import validate_email_address, validate_password
from .validators import validate_competition_password

bp = Blueprint("super_admin", __name__, url_prefix="/super-admin")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated and isinstance(current_user, SuperAdmin):
        return redirect(url_for("super_admin.dashboard"))

    if request.method == "POST":
        email_raw = request.form.get("email", "")
        password = request.form.get("password", "")
        try:
            email = validate_email_address(email_raw)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("super_admin/login.html")

        sa = SuperAdmin.query.filter_by(email=email).first()
        if sa is None or not sa.check_password(password):
            flash("Invalid email or password.", "error")
            return render_template("super_admin/login.html")

        login_user(sa)
        next_url = request.args.get("next")
        if next_url:
            return redirect(next_url)
        return redirect(url_for("super_admin.dashboard"))

    return render_template("super_admin/login.html")


@bp.route("/logout")
def logout():
    if current_user.is_authenticated and isinstance(current_user, SuperAdmin):
        logout_user()
    return redirect(url_for("super_admin.login"))


@bp.route("/")
@super_admin_required
def dashboard():
    societies = Society.query.order_by(Society.name).all()
    return render_template("super_admin/dashboard.html", societies=societies)


@bp.route("/societies/new", methods=["GET", "POST"])
@super_admin_required
def society_new():
    if request.method == "POST":
        name = (request.form.get("society_name") or "").strip()
        email_raw = request.form.get("admin_email", "")
        password = request.form.get("admin_password", "")
        player_password = request.form.get("player_password", "")
        if not name:
            flash("Society name is required.", "error")
            return render_template("super_admin/society_new.html")
        try:
            email = validate_email_address(email_raw)
            validate_password(password)
            validate_competition_password(player_password)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("super_admin/society_new.html")

        if Admin.query.filter_by(email=email).first():
            flash("That email is already used by a society admin.", "error")
            return render_template("super_admin/society_new.html")

        soc = Society(name=name, register_token=Society.generate_register_token())
        soc.set_player_password(player_password)
        db.session.add(soc)
        db.session.flush()
        admin = Admin(email=email, society_id=soc.id)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        flash(
            f"Society “{name}” created with first admin {email} and a shared player password.",
            "success",
        )
        return redirect(url_for("super_admin.dashboard"))

    return render_template("super_admin/society_new.html")


@bp.route("/societies/<int:society_id>/admins")
@super_admin_required
def society_admins(society_id: int):
    society = Society.query.get_or_404(society_id)
    admins = society.admins.order_by(Admin.email).all()
    return render_template(
        "super_admin/society_admins.html", society=society, admins=admins
    )


@bp.route(
    "/societies/<int:society_id>/admins/<int:admin_id>/reset-password",
    methods=["POST"],
)
@super_admin_required
def society_admin_reset_password(society_id: int, admin_id: int):
    society = Society.query.get_or_404(society_id)
    admin = Admin.query.get_or_404(admin_id)
    if admin.society_id != society.id:
        flash("That admin does not belong to this society.", "error")
        return redirect(url_for("super_admin.society_admins", society_id=society.id))

    password = request.form.get("new_password", "")
    confirm = request.form.get("new_password_confirm", "")
    try:
        validate_password(password)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("super_admin.society_admins", society_id=society.id))
    if password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("super_admin.society_admins", society_id=society.id))

    admin.set_password(password)
    db.session.commit()
    flash(f"Password reset for {admin.email}.", "success")
    return redirect(url_for("super_admin.society_admins", society_id=society.id))


def _form_bool_locked() -> bool:
    v = (request.form.get("locked") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


@bp.route("/societies/<int:society_id>/locked", methods=["POST"])
@super_admin_required
def society_set_locked(society_id: int):
    society = Society.query.get_or_404(society_id)
    society.locked = _form_bool_locked()
    db.session.commit()
    if society.locked:
        flash(f"Society “{society.name}” is now locked. Society admins cannot sign in.", "success")
    else:
        flash(f"Society “{society.name}” is unlocked.", "success")
    if request.form.get("return_to") == "society_admins":
        return redirect(url_for("super_admin.society_admins", society_id=society.id))
    return redirect(url_for("super_admin.dashboard"))


@bp.route("/account", methods=["GET", "POST"])
@super_admin_required
def account():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm = request.form.get("new_password_confirm", "")
        if not current_user.check_password(current_pw):
            flash("Current password is incorrect.", "error")
            return render_template("super_admin/account.html")
        try:
            validate_password(new_pw)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("super_admin/account.html")
        if new_pw != confirm:
            flash("New passwords do not match.", "error")
            return render_template("super_admin/account.html")
        current_user.set_password(new_pw)
        db.session.commit()
        flash("Your super admin password was updated.", "success")
        return redirect(url_for("super_admin.account"))

    return render_template("super_admin/account.html")


@bp.route("/super-admins")
@super_admin_required
def super_admins_list():
    super_admins = SuperAdmin.query.order_by(SuperAdmin.email).all()
    return render_template("super_admin/super_admins.html", super_admins=super_admins)


@bp.route("/super-admins/new", methods=["POST"])
@super_admin_required
def super_admin_new():
    email_raw = request.form.get("email", "")
    password = request.form.get("password", "")
    confirm = request.form.get("password_confirm", "")
    try:
        email = validate_email_address(email_raw)
        validate_password(password)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("super_admin.super_admins_list"))
    if password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("super_admin.super_admins_list"))
    if SuperAdmin.query.filter_by(email=email).first():
        flash("A super admin with that email already exists.", "error")
        return redirect(url_for("super_admin.super_admins_list"))
    sa = SuperAdmin(email=email)
    sa.set_password(password)
    db.session.add(sa)
    db.session.commit()
    flash(f"Super admin {email} created.", "success")
    return redirect(url_for("super_admin.super_admins_list"))


@bp.route("/super-admins/<int:super_admin_id>/delete", methods=["POST"])
@super_admin_required
def super_admin_delete(super_admin_id: int):
    target = SuperAdmin.query.get_or_404(super_admin_id)
    if target.id == current_user.id:
        flash("You cannot delete the account you are signed in as.", "error")
        return redirect(url_for("super_admin.super_admins_list"))
    if SuperAdmin.query.count() <= 1:
        flash("Cannot delete the last super admin.", "error")
        return redirect(url_for("super_admin.super_admins_list"))
    db.session.delete(target)
    db.session.commit()
    flash(f"Removed super admin {target.email}.", "success")
    return redirect(url_for("super_admin.super_admins_list"))
