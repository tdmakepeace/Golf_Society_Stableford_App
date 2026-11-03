from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from . import db
from .decorators import user_required
from .models import Competition, CompetitionPlayer, Hole, Society, User
from .player_helpers import apply_user_password
from .scoring_helpers import (
    player_result,
    save_competition_scores,
    save_submitted_hole_scores,
)
from .validators import validate_email_address, validate_password

PLAYER_COMPETITION_IDS = "player_competition_ids"

bp = Blueprint("user", __name__)


def _can_authenticate_user(user: User, password: str) -> bool:
    if user.check_password(password):
        return True
    if user.society and user.society.check_player_password(password):
        return True
    return False


def _society_for_register_token(token: str) -> Society | None:
    society = Society.query.filter_by(register_token=token).first()
    if society is None or society.locked:
        return None
    return society


@bp.route("/register/<token>", methods=["GET", "POST"])
def register(token: str):
    if current_user.is_authenticated and isinstance(current_user, User):
        return redirect(url_for("user.dashboard"))

    society = _society_for_register_token(token)
    if society is None:
        flash("This registration link is invalid or no longer available.", "error")
        return redirect(url_for("user.login"))

    if request.method == "POST":
        email_raw = request.form.get("email", "")
        password = request.form.get("password", "")
        try:
            email = validate_email_address(email_raw)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("user/register.html", society=society)

        existing = User.query.filter_by(email=email).first()
        if existing:
            if existing.society_id != society.id:
                flash("That email is already registered with another society.", "error")
                return render_template("user/register.html", society=society)
            if not existing.is_deleted:
                flash("That email is already registered. Sign in instead.", "error")
                return render_template("user/register.html", society=society)
            try:
                apply_user_password(existing, password, society)
            except ValueError as e:
                flash(str(e), "error")
                return render_template("user/register.html", society=society)
            existing.is_deleted = False
            db.session.commit()
            login_user(existing)
            flash(f"Welcome back to {society.name}!", "success")
            return redirect(url_for("user.dashboard"))

        user = User(email=email, society_id=society.id)
        try:
            apply_user_password(user, password, society)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("user/register.html", society=society)

        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash(f"Welcome to {society.name}!", "success")
        return redirect(url_for("user.dashboard"))

    return render_template("user/register.html", society=society)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated and isinstance(current_user, User):
        return redirect(url_for("user.dashboard"))

    if request.method == "POST":
        email_raw = request.form.get("email", "")
        password = request.form.get("password", "")
        try:
            email = validate_email_address(email_raw)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("user/login.html")

        user = User.query.filter_by(email=email).first()
        if user is None:
            flash("Invalid email or password.", "error")
            return render_template("user/login.html")

        if not _can_authenticate_user(user, password):
            flash(
                "Invalid email or password.",
                "error",
            )
            return render_template("user/login.html")

        login_user(user)
        next_url = request.args.get("next")
        if next_url:
            return redirect(next_url)
        return redirect(url_for("user.dashboard"))

    return render_template("user/login.html")


@bp.route("/logout")
def logout():
    if current_user.is_authenticated and isinstance(current_user, User):
        logout_user()
    return redirect(url_for("user.login"))


@bp.route("/player")
@user_required
def dashboard():
    entries = (
        CompetitionPlayer.query.filter_by(user_id=current_user.id)
        .join(Competition)
        .order_by(Competition.name)
        .all()
    )
    summaries = []
    for e in entries:
        pr = player_result(e.competition, current_user)
        summaries.append(
            {
                "competition": e.competition,
                "total_points": pr["total_points"],
                "playing_handicap": pr["playing_handicap"],
            }
        )
    return render_template("user/dashboard.html", entries=summaries)


def _player_competition(comp_id: int):
    comp = Competition.query.get_or_404(comp_id)
    entry = CompetitionPlayer.query.filter_by(
        competition_id=comp.id, user_id=current_user.id
    ).first()
    return comp, entry


def _course_holes(comp: Competition):
    return (
        Hole.query.filter_by(course_id=comp.course_id)
        .order_by(Hole.hole_number)
        .all()
    )


def _first_open_hole(rows: list[dict]) -> int:
    for row in rows:
        if row["gross"] is None:
            return row["hole"]
    return rows[0]["hole"] if rows else 1


@bp.route("/player/competition/<int:comp_id>", methods=["GET", "POST"])
@user_required
def competition_scorecard(comp_id: int):
    comp, entry = _player_competition(comp_id)
    if not entry:
        flash("You are not in this competition.", "error")
        return redirect(url_for("user.dashboard"))

    holes = _course_holes(comp)

    if request.method == "POST":
        if comp.locked:
            flash("This competition is locked. Scores cannot be changed.", "error")
            return redirect(url_for("user.competition_scorecard", comp_id=comp.id))

        err = save_competition_scores(comp, current_user, holes, request.form)
        if err:
            flash(err, "error")
            return redirect(url_for("user.competition_scorecard", comp_id=comp.id))
        db.session.commit()
        flash("Scores saved.", "success")
        return redirect(url_for("user.competition_scorecard", comp_id=comp.id))

    pr = player_result(comp, current_user)
    phc = pr["playing_handicap"]
    si_flat = phc > 0 and phc % 18 == 0
    return render_template(
        "user/scorecard.html",
        competition=comp,
        scorecard_readonly=comp.locked,
        handicap_splits_evenly_by_18=si_flat,
        rows=pr["rows"],
        total_points=pr["total_points"],
        playing_handicap=pr["playing_handicap"],
        course_par_total=pr["course_par_total"],
        gross_total=pr["gross_total"],
        target_gross_total=pr["target_gross_total"],
    )


@bp.route("/player/competition/<int:comp_id>/match", methods=["GET", "POST"])
@user_required
def competition_match(comp_id: int):
    comp, entry = _player_competition(comp_id)
    if not entry:
        flash("You are not in this competition.", "error")
        return redirect(url_for("user.dashboard"))

    holes = _course_holes(comp)
    if not holes:
        flash("This course has no holes yet.", "error")
        return redirect(url_for("user.dashboard"))

    hole_numbers = [h.hole_number for h in holes]

    def hole_url(hole_number: int):
        return url_for(
            "user.competition_match", comp_id=comp.id, hole=hole_number
        )

    if request.method == "POST":
        try:
            current = int(request.form.get("hole", ""))
        except ValueError:
            current = hole_numbers[0]
        if current not in hole_numbers:
            current = hole_numbers[0]

        if comp.locked:
            flash("This competition is locked. Scores cannot be changed.", "error")
            return redirect(hole_url(current))

        err = save_submitted_hole_scores(comp, current_user, holes, request.form)
        if err:
            flash(err, "error")
            return redirect(hole_url(current))
        db.session.commit()

        nav = request.form.get("nav", "stay")
        idx = hole_numbers.index(current)
        if nav == "prev" and idx > 0:
            return redirect(hole_url(hole_numbers[idx - 1]))
        if nav == "next" and idx < len(hole_numbers) - 1:
            return redirect(hole_url(hole_numbers[idx + 1]))
        return redirect(hole_url(current))

    pr = player_result(comp, current_user)
    rows = pr["rows"]
    requested = request.args.get("hole", type=int)
    if requested in hole_numbers:
        current = requested
    else:
        current = _first_open_hole(rows)
    row = next(r for r in rows if r["hole"] == current)
    idx = hole_numbers.index(current)
    phc = pr["playing_handicap"]
    return render_template(
        "user/match.html",
        competition=comp,
        scorecard_readonly=comp.locked,
        handicap_splits_evenly_by_18=phc > 0 and phc % 18 == 0,
        row=row,
        hole_index=idx + 1,
        hole_count=len(hole_numbers),
        has_prev=idx > 0,
        has_next=idx < len(hole_numbers) - 1,
        prev_hole=hole_numbers[idx - 1] if idx > 0 else None,
        next_hole=hole_numbers[idx + 1] if idx < len(hole_numbers) - 1 else None,
        total_points=pr["total_points"],
        playing_handicap=pr["playing_handicap"],
        holes_entered=pr["holes_entered"],
        progress_pct=round((idx + 1) / len(hole_numbers) * 100),
    )


@bp.route("/player/account", methods=["GET", "POST"])
@user_required
def account():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not _can_authenticate_user(current_user, current_pw):
            flash("Current password is incorrect.", "error")
            return render_template("user/account.html")
        if new_pw != confirm:
            flash("New passwords do not match.", "error")
            return render_template("user/account.html")
        try:
            validate_password(new_pw)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("user/account.html")

        current_user.set_password(new_pw)
        db.session.commit()
        flash("Your password has been updated.", "success")
        return redirect(url_for("user.account"))

    return render_template("user/account.html")
