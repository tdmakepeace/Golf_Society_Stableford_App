from __future__ import annotations

from types import SimpleNamespace

from flask import Blueprint, flash, make_response, redirect, render_template, request, url_for
from sqlalchemy import or_
from flask_login import current_user, login_user, logout_user

from . import db
from .csv_helpers import iter_society_users_from_csv
from .csv_players import iter_players_from_csv
from .decorators import admin_required
from .models import Admin, Competition, CompetitionPlayer, Course, Hole, Score, Society, User
from .player_helpers import apply_user_password
from .scoring_helpers import competition_leaderboard, player_result, save_competition_scores
from .site_settings import player_registration_url
from .validators import (
    normalize_friendly_name,
    validate_email_address,
    validate_competition_password,
    validate_password,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _courses_query(search: str = ""):
    q = Course.query.order_by(Course.name, Course.postcode)
    term = (search or "").strip()
    if term:
        like = f"%{term}%"
        q = q.filter(or_(Course.name.ilike(like), Course.postcode.ilike(like)))
    return q


def _is_popup_request() -> bool:
    return (request.args.get("popup") or request.form.get("popup") or "") == "1"


def _latest_previous_handicap_for_user(comp: Competition, user_id: int) -> int:
    prior = (
        CompetitionPlayer.query.join(Competition)
        .join(Admin, Competition.admin_id == Admin.id)
        .filter(
            CompetitionPlayer.user_id == user_id,
            Competition.id != comp.id,
            Competition.id < comp.id,
            Admin.society_id == current_user.society_id,
        )
        .order_by(Competition.id.desc())
        .first()
    )
    if prior:
        return prior.playing_handicap
    return 0


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated and isinstance(current_user, Admin):
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        email_raw = request.form.get("email", "")
        password = request.form.get("password", "")
        try:
            email = validate_email_address(email_raw)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("admin/login.html")

        admin = Admin.query.filter_by(email=email).first()
        if admin is None or not admin.check_password(password):
            flash("Invalid email or password.", "error")
            return render_template("admin/login.html")

        society = db.session.get(Society, admin.society_id)
        if society is not None and society.locked:
            flash(
                "This society is locked. Contact a super admin to unlock it.",
                "error",
            )
            return render_template("admin/login.html")

        login_user(admin)
        next_url = request.args.get("next")
        if next_url:
            return redirect(next_url)
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/login.html")


@bp.route("/logout")
def logout():
    if current_user.is_authenticated and isinstance(current_user, Admin):
        logout_user()
    return redirect(url_for("admin.login"))


@bp.route("/")
@admin_required
def dashboard():
    course_search = (request.args.get("course_q") or "").strip()
    courses = _courses_query(course_search).all()
    comps = (
        Competition.query.filter_by(admin_id=current_user.id)
        .order_by(Competition.name)
        .all()
    )
    return render_template(
        "admin/dashboard.html",
        society=current_user.society,
        courses=courses,
        course_search=course_search,
        course_total_count=_courses_query("").count(),
        competitions=comps,
    )


def _parse_course_holes_from_form(form, *, require_unique_si: bool = True):
    """Return (pars, sis) lists or raise ValueError."""
    pars = []
    sis = []
    for i in range(1, 19):
        try:
            p = int(form.get(f"par_{i}", "4"))
            si = int(form.get(f"si_{i}", str(i)))
        except (TypeError, ValueError):
            raise ValueError("Invalid par or stroke index.")
        if p < 3 or p > 6:
            raise ValueError(f"Hole {i}: par must be between 3 and 6.")
        if si < 1 or si > 18:
            raise ValueError(f"Hole {i}: stroke index must be 1–18.")
        pars.append(p)
        sis.append(si)
    if require_unique_si and len(set(sis)) != 18:
        dup_holes = _duplicate_si_hole_numbers(sis)
        holes_str = ", ".join(str(h) for h in sorted(dup_holes))
        raise ValueError(
            f"Stroke indexes must be unique 1–18 across all holes. "
            f"Duplicate values highlighted on hole(s): {holes_str}."
        )
    return pars, sis


def _duplicate_si_hole_numbers(sis: list[int]) -> set[int]:
    """Return 1-based hole numbers whose stroke index appears more than once."""
    by_si: dict[int, list[int]] = {}
    for i, si in enumerate(sis):
        by_si.setdefault(si, []).append(i + 1)
    dup_holes: set[int] = set()
    for hole_nums in by_si.values():
        if len(hole_nums) > 1:
            dup_holes.update(hole_nums)
    return dup_holes


def _holes_from_form_for_display(form) -> list[SimpleNamespace]:
    """Build hole rows from submitted form values for re-rendering after validation errors."""
    holes: list[SimpleNamespace] = []
    for i in range(1, 19):
        par_raw = form.get(f"par_{i}", "")
        si_raw = form.get(f"si_{i}", "")
        try:
            par = int(par_raw)
        except (TypeError, ValueError):
            par = 4
        try:
            si = int(si_raw)
        except (TypeError, ValueError):
            si = i
        holes.append(
            SimpleNamespace(hole_number=i, par=par, stroke_index=si)
        )
    return holes


def _duplicate_si_holes_from_form(form) -> set[int]:
    try:
        _, sis = _parse_course_holes_from_form(form, require_unique_si=False)
    except ValueError:
        return set()
    return _duplicate_si_hole_numbers(sis)


def _course_form_error(
    course,
    *,
    form_name: str,
    form_postcode: str,
    form,
):
    form_holes = _holes_from_form_for_display(form)
    return render_template(
        "admin/course_form.html",
        course=course,
        holes=form_holes,
        form_name=form_name,
        form_postcode=form_postcode,
        duplicate_si_holes=_duplicate_si_holes_from_form(form),
    )


@bp.route("/courses/new", methods=["GET", "POST"])
@admin_required
def course_new():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        postcode = (request.form.get("postcode") or "").strip()
        if not name:
            flash("Course name is required.", "error")
            return _course_form_error(
                None,
                form_name=name,
                form_postcode=postcode,
                form=request.form,
            )

        try:
            pars, sis = _parse_course_holes_from_form(request.form)
        except ValueError as e:
            flash(str(e), "error")
            return _course_form_error(
                None,
                form_name=name,
                form_postcode=postcode,
                form=request.form,
            )

        c = Course(
            name=name,
            postcode=postcode,
            created_by_admin_id=current_user.id,
        )
        db.session.add(c)
        db.session.flush()
        for i in range(18):
            db.session.add(
                Hole(
                    course_id=c.id,
                    hole_number=i + 1,
                    par=pars[i],
                    stroke_index=sis[i],
                )
            )
        db.session.commit()
        flash("Course created.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/course_form.html", course=None, holes=[])


@bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
@admin_required
def course_edit(course_id: int):
    c = Course.query.get_or_404(course_id)

    holes = Hole.query.filter_by(course_id=c.id).order_by(Hole.hole_number).all()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        postcode = (request.form.get("postcode") or "").strip()
        if not name:
            flash("Course name is required.", "error")
            return _course_form_error(
                c,
                form_name=name,
                form_postcode=postcode,
                form=request.form,
            )

        try:
            pars, sis = _parse_course_holes_from_form(request.form)
        except ValueError as e:
            flash(str(e), "error")
            return _course_form_error(
                c,
                form_name=name,
                form_postcode=postcode,
                form=request.form,
            )

        c.name = name
        c.postcode = postcode
        for idx, h in enumerate(holes):
            h.par = pars[idx]
            h.stroke_index = sis[idx]
        db.session.commit()
        flash("Course updated.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/course_form.html", course=c, holes=holes)


@bp.route("/competitions/new", methods=["GET", "POST"])
@admin_required
def competition_new():
    course_search = (request.args.get("course_q") or request.form.get("course_q") or "").strip()
    courses = _courses_query(course_search).all()
    if not Course.query.first():
        flash("Add a course first (shared with all societies).", "error")
        return redirect(url_for("admin.course_new"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        try:
            course_id = int(request.form.get("course_id", "0"))
        except (TypeError, ValueError):
            course_id = 0
        course = db.session.get(Course, course_id)
        if not name or not course:
            flash("Competition name and course are required.", "error")
            return render_template(
                "admin/competition_new.html",
                courses=courses,
                course_search=course_search,
                selected_id=course_id if course_id else None,
            )

        comp = Competition(
            name=name, course_id=course.id, admin_id=current_user.id
        )
        db.session.add(comp)
        db.session.commit()
        flash("Competition created.", "success")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    return render_template(
        "admin/competition_new.html",
        courses=courses,
        course_search=course_search,
    )


@bp.route("/competitions/<int:comp_id>")
@admin_required
def competition_detail(comp_id: int):
    comp = Competition.query.get_or_404(comp_id)
    if comp.admin_id != current_user.id:
        flash("Not your competition.", "error")
        return redirect(url_for("admin.dashboard"))

    players = (
        CompetitionPlayer.query.filter_by(competition_id=comp.id)
        .join(User)
        .order_by(User.email)
        .all()
    )
    entered_user_ids = [p.user_id for p in players]
    available_users_q = User.query.filter_by(
        society_id=current_user.society_id, is_deleted=False
    )
    if entered_user_ids:
        available_users_q = available_users_q.filter(~User.id.in_(entered_user_ids))
    available_users = available_users_q.order_by(User.email).all()
    return render_template(
        "admin/competition_detail.html",
        competition=comp,
        players=players,
        available_users=available_users,
    )


@bp.route("/competitions/<int:comp_id>/players", methods=["POST"])
@admin_required
def competition_add_player(comp_id: int):
    comp = Competition.query.get_or_404(comp_id)
    if comp.admin_id != current_user.id:
        flash("Not your competition.", "error")
        return redirect(url_for("admin.dashboard"))
    if comp.locked:
        flash("This competition is locked. Unlock it to change the player list.", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    email_raw = request.form.get("email", "")
    try:
        playing_hc = int(request.form.get("playing_handicap", "0"))
    except (TypeError, ValueError):
        playing_hc = 0

    try:
        email = validate_email_address(email_raw)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    if playing_hc < 0 or playing_hc > 54:
        flash("Playing handicap must be between 0 and 54.", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    user = User.query.filter_by(
        email=email, society_id=current_user.society_id, is_deleted=False
    ).first()
    if user is None:
        flash(
            "That player is not in this society yet. Create them under Society players first.",
            "error",
        )
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    existing = CompetitionPlayer.query.filter_by(
        competition_id=comp.id, user_id=user.id
    ).first()
    if existing:
        existing.playing_handicap = playing_hc
        flash("Player updated (handicap).", "success")
    else:
        if request.form.get("playing_handicap", "").strip() == "":
            playing_hc = _latest_previous_handicap_for_user(comp, user.id)
        db.session.add(
            CompetitionPlayer(
                competition_id=comp.id,
                user_id=user.id,
                playing_handicap=playing_hc,
            )
        )
        flash("Player added to competition.", "success")

    db.session.commit()
    return redirect(url_for("admin.competition_detail", comp_id=comp.id))


@bp.route("/competitions/<int:comp_id>/players/<int:user_id>/delete", methods=["POST"])
@admin_required
def competition_remove_player(comp_id: int, user_id: int):
    comp = Competition.query.get_or_404(comp_id)
    if comp.admin_id != current_user.id:
        flash("Not your competition.", "error")
        return redirect(url_for("admin.dashboard"))
    if comp.locked:
        flash("This competition is locked. Unlock it to remove players.", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    entry = CompetitionPlayer.query.filter_by(
        competition_id=comp.id, user_id=user_id
    ).first()
    if not entry:
        flash("That player is not in this competition.", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    Score.query.filter_by(competition_id=comp.id, user_id=user_id).delete(
        synchronize_session=False
    )
    db.session.delete(entry)
    db.session.commit()
    flash("Player removed from this competition (their scores for this event were deleted).", "success")
    return redirect(url_for("admin.competition_detail", comp_id=comp.id))


@bp.route("/competitions/<int:comp_id>/players/<int:user_id>/handicap", methods=["POST"])
@admin_required
def competition_update_player_handicap(comp_id: int, user_id: int):
    comp = Competition.query.get_or_404(comp_id)
    if comp.admin_id != current_user.id:
        flash("Not your competition.", "error")
        return redirect(url_for("admin.dashboard"))
    if comp.locked:
        flash("This competition is locked. Unlock it to edit player handicaps.", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    entry = CompetitionPlayer.query.filter_by(
        competition_id=comp.id, user_id=user_id
    ).first()
    if not entry:
        flash("That player is not in this competition.", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    try:
        playing_hc = int(request.form.get("playing_handicap", "0"))
    except (TypeError, ValueError):
        flash("Playing handicap must be a whole number between 0 and 54.", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    if playing_hc < 0 or playing_hc > 54:
        flash("Playing handicap must be between 0 and 54.", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    entry.playing_handicap = playing_hc
    db.session.commit()
    flash(f"Updated handicap for {entry.user.display_label}.", "success")
    return redirect(url_for("admin.competition_detail", comp_id=comp.id))


@bp.route("/competitions/<int:comp_id>/players/<int:user_id>/scores", methods=["GET", "POST"])
@admin_required
def competition_player_scores(comp_id: int, user_id: int):
    comp = Competition.query.get_or_404(comp_id)
    if comp.admin_id != current_user.id:
        flash("Not your competition.", "error")
        return redirect(url_for("admin.dashboard"))

    entry = CompetitionPlayer.query.filter_by(
        competition_id=comp.id, user_id=user_id
    ).first()
    if not entry:
        flash("That player is not in this competition.", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    user = entry.user
    holes = (
        Hole.query.filter_by(course_id=comp.course_id)
        .order_by(Hole.hole_number)
        .all()
    )

    if request.method == "POST":
        err = save_competition_scores(comp, user, holes, request.form)
        if err:
            flash(err, "error")
            return redirect(
                url_for("admin.competition_player_scores", comp_id=comp.id, user_id=user_id)
            )
        db.session.commit()
        flash(f"Scores saved for {user.display_label}.", "success")
        return redirect(
            url_for("admin.competition_player_scores", comp_id=comp.id, user_id=user_id)
        )

    pr = player_result(comp, user)
    phc = pr["playing_handicap"]
    si_flat = phc > 0 and phc % 18 == 0
    return render_template(
        "admin/player_scorecard.html",
        competition=comp,
        player=user,
        handicap_splits_evenly_by_18=si_flat,
        rows=pr["rows"],
        total_points=pr["total_points"],
        playing_handicap=pr["playing_handicap"],
        course_par_total=pr["course_par_total"],
        gross_total=pr["gross_total"],
        target_gross_total=pr["target_gross_total"],
    )


@bp.route("/competitions/<int:comp_id>/locked", methods=["POST"])
@admin_required
def competition_set_locked(comp_id: int):
    comp = Competition.query.get_or_404(comp_id)
    if comp.admin_id != current_user.id:
        flash("Not your competition.", "error")
        return redirect(url_for("admin.dashboard"))

    raw = (request.form.get("locked") or "").strip().lower()
    comp.locked = raw in ("1", "true", "on", "yes")
    db.session.commit()
    flash(
        "Competition locked. Players cannot edit scores; roster changes are disabled."
        if comp.locked
        else "Competition unlocked.",
        "success",
    )
    return redirect(url_for("admin.competition_detail", comp_id=comp.id))


@bp.route("/competitions/<int:comp_id>/results")
@admin_required
def competition_results(comp_id: int):
    comp = Competition.query.get_or_404(comp_id)
    if comp.admin_id != current_user.id:
        flash("Not your competition.", "error")
        return redirect(url_for("admin.dashboard"))

    board = competition_leaderboard(comp)
    holes = (
        Hole.query.filter_by(course_id=comp.course_id)
        .order_by(Hole.hole_number)
        .all()
    )
    course_par_total = sum(h.par for h in holes)
    return render_template(
        "admin/results.html",
        competition=comp,
        leaderboard=board,
        holes=holes,
        course_par_total=course_par_total,
    )


@bp.route("/competitions/<int:comp_id>/results.pdf")
@admin_required
def competition_results_pdf(comp_id: int):
    comp = Competition.query.get_or_404(comp_id)
    if comp.admin_id != current_user.id:
        flash("Not your competition.", "error")
        return redirect(url_for("admin.dashboard"))

    board = competition_leaderboard(comp)
    holes = (
        Hole.query.filter_by(course_id=comp.course_id)
        .order_by(Hole.hole_number)
        .all()
    )
    course_par_total = sum(h.par for h in holes)
    html = render_template(
        "admin/results_pdf.html",
        competition=comp,
        leaderboard=board,
        holes=holes,
        course_par_total=course_par_total,
    )
    from .pdf_export import html_to_pdf_bytes

    pdf = html_to_pdf_bytes(html)
    filename = f"{comp.name.replace(' ', '_')}_results.pdf"
    resp = make_response(pdf)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@bp.route("/account", methods=["GET", "POST"])
@admin_required
def account():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not current_user.check_password(current_pw):
            flash("Current password is incorrect.", "error")
            return render_template("admin/account.html")
        if new_pw != confirm:
            flash("New passwords do not match.", "error")
            return render_template("admin/account.html")
        try:
            validate_password(new_pw)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("admin/account.html")
        current_user.set_password(new_pw)
        db.session.commit()
        flash("Your password has been updated.", "success")
        return redirect(url_for("admin.account"))

    return render_template("admin/account.html")


@bp.route("/admins")
@admin_required
def admins_list():
    admins = (
        Admin.query.filter_by(society_id=current_user.society_id)
        .order_by(Admin.email)
        .all()
    )
    return render_template("admin/admins.html", admins=admins)


@bp.route("/admins/new", methods=["POST"])
@admin_required
def admin_new():
    email_raw = request.form.get("email", "")
    password = request.form.get("password", "")
    try:
        email = validate_email_address(email_raw)
        validate_password(password)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.admins_list"))

    if Admin.query.filter_by(email=email).first():
        flash("An admin with that email already exists.", "error")
        return redirect(url_for("admin.admins_list"))

    admin = Admin(email=email, society_id=current_user.society_id)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    flash("Admin created.", "success")
    return redirect(url_for("admin.admins_list"))


@bp.route("/admins/<int:admin_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit(admin_id: int):
    target = Admin.query.get_or_404(admin_id)
    if target.society_id != current_user.society_id:
        flash("Not a society admin you can manage.", "error")
        return redirect(url_for("admin.admins_list"))

    if request.method == "POST":
        email_raw = request.form.get("email", "")
        new_password = request.form.get("new_password", "")
        try:
            email = validate_email_address(email_raw)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("admin/admin_edit.html", edit_admin=target)

        other = Admin.query.filter(Admin.email == email, Admin.id != target.id).first()
        if other:
            flash("That email is already in use.", "error")
            return render_template("admin/admin_edit.html", edit_admin=target)

        target.email = email
        if new_password:
            try:
                validate_password(new_password)
            except ValueError as e:
                flash(str(e), "error")
                return render_template("admin/admin_edit.html", edit_admin=target)
            target.set_password(new_password)

        db.session.commit()
        flash("Admin updated.", "success")
        return redirect(url_for("admin.admins_list"))

    return render_template("admin/admin_edit.html", edit_admin=target)


@bp.route("/admins/<int:admin_id>/delete", methods=["POST"])
@admin_required
def admin_delete(admin_id: int):
    target = Admin.query.get_or_404(admin_id)
    if target.society_id != current_user.society_id:
        flash("Not a society admin you can manage.", "error")
        return redirect(url_for("admin.admins_list"))

    n_same = Admin.query.filter_by(society_id=current_user.society_id).count()
    if n_same <= 1:
        flash("Cannot delete the last admin in this society.", "error")
        return redirect(url_for("admin.admins_list"))

    if target.competitions.count() > 0:
        flash(
            "Cannot delete an admin who still owns competitions. Delete those first.",
            "error",
        )
        return redirect(url_for("admin.admins_list"))

    was_self = target.id == current_user.id
    db.session.delete(target)
    db.session.commit()
    if was_self:
        logout_user()
        flash("Your admin account was removed.", "success")
        return redirect(url_for("admin.login"))

    flash("Admin removed.", "success")
    return redirect(url_for("admin.admins_list"))


@bp.route("/courses/<int:course_id>/delete", methods=["POST"])
@admin_required
def course_delete(course_id: int):
    c = Course.query.get_or_404(course_id)

    if c.competitions.count() > 0:
        flash("Cannot delete a course that is used by a competition.", "error")
        return redirect(url_for("admin.dashboard"))

    db.session.delete(c)
    db.session.commit()
    flash("Course deleted.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/competitions/<int:comp_id>/delete", methods=["POST"])
@admin_required
def competition_delete(comp_id: int):
    comp = Competition.query.get_or_404(comp_id)
    if comp.admin_id != current_user.id:
        flash("Not your competition.", "error")
        return redirect(url_for("admin.dashboard"))

    db.session.delete(comp)
    db.session.commit()
    flash("Competition deleted.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/users/player-password", methods=["POST"])
@admin_required
def society_set_player_password():
    pw = request.form.get("society_player_password", "")
    try:
        validate_competition_password(pw)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.society_users"))

    current_user.society.set_player_password(pw)
    db.session.commit()
    flash(
        "Society player password updated. Players can sign in with this shared password.",
        "success",
    )
    return redirect(url_for("admin.society_users"))


@bp.route("/competitions/<int:comp_id>/import-players", methods=["POST"])
@admin_required
def competition_import_players(comp_id: int):
    comp = Competition.query.get_or_404(comp_id)
    if comp.admin_id != current_user.id:
        flash("Not your competition.", "error")
        return redirect(url_for("admin.dashboard"))
    if comp.locked:
        flash("This competition is locked. Unlock it to import players.", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    upload = request.files.get("csv_file")
    if not upload or not upload.filename:
        flash("Choose a CSV file to upload.", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    try:
        raw = upload.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("Could not read CSV as UTF-8.", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    try:
        rows = list(iter_players_from_csv(raw))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    if not rows:
        flash("No player rows found in CSV.", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp.id))

    added = 0
    updated = 0
    skipped: list[str] = []
    for email_raw, playing_hc in rows:
        try:
            email = validate_email_address(email_raw)
        except ValueError:
            skipped.append(f"invalid email {email_raw!r}")
            continue
        if playing_hc < 0 or playing_hc > 54:
            skipped.append(f"{email}: handicap must be 0–54")
            continue

        user = User.query.filter_by(
            email=email, society_id=current_user.society_id, is_deleted=False
        ).first()
        if user is None:
            skipped.append(f"{email}: not an active society player")
            continue

        existing = CompetitionPlayer.query.filter_by(
            competition_id=comp.id, user_id=user.id
        ).first()
        if existing:
            existing.playing_handicap = playing_hc
            updated += 1
        else:
            db.session.add(
                CompetitionPlayer(
                    competition_id=comp.id,
                    user_id=user.id,
                    playing_handicap=playing_hc,
                )
            )
            added += 1

    db.session.commit()
    msg = (
        f"Import finished: {added} added to this competition, {updated} handicap updates. "
        f"Players sign in with their email and society/player password."
    )
    if skipped:
        msg += f" Skipped {len(skipped)} row(s): " + "; ".join(skipped[:8])
        if len(skipped) > 8:
            msg += "…"
    flash(msg, "success")
    return redirect(url_for("admin.competition_detail", comp_id=comp.id))


@bp.route("/users")
@admin_required
def society_users():
    society = current_user.society
    if not society.register_token:
        society.ensure_register_token()
        db.session.commit()
    users = (
        User.query.filter_by(society_id=current_user.society_id, is_deleted=False)
        .order_by(User.email)
        .all()
    )
    archived_users = (
        User.query.filter_by(society_id=current_user.society_id, is_deleted=True)
        .order_by(User.email)
        .all()
    )
    return render_template(
        "admin/users.html",
        users=users,
        archived_users=archived_users,
        society=society,
        register_url=player_registration_url(society.register_token),
        popup=_is_popup_request(),
        player_created=request.args.get("created") == "1",
    )


@bp.route("/users/register-link/regenerate", methods=["POST"])
@admin_required
def society_regenerate_register_token():
    society = current_user.society
    society.register_token = Society.generate_register_token()
    db.session.commit()
    flash(
        "Registration link updated. Share the new link — old links no longer work.",
        "success",
    )
    return redirect(url_for("admin.society_users"))


@bp.route("/users/new", methods=["POST"])
@admin_required
def society_user_new():
    email_raw = request.form.get("email", "")
    password = request.form.get("password", "")
    friendly_name_raw = request.form.get("friendly_name", "")
    popup = _is_popup_request()
    try:
        email = validate_email_address(email_raw)
        friendly_name = normalize_friendly_name(friendly_name_raw)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.society_users", popup=1 if popup else None))

    existing_any = User.query.filter_by(email=email).first()
    if existing_any:
        flash("That email is already in use.", "error")
        return redirect(url_for("admin.society_users", popup=1 if popup else None))

    user = User(
        email=email,
        society_id=current_user.society_id,
        friendly_name=friendly_name,
    )
    try:
        apply_user_password(user, password, current_user.society)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.society_users", popup=1 if popup else None))

    db.session.add(user)
    db.session.commit()
    flash("Society player created.", "success")
    if popup:
        return redirect(url_for("admin.society_users", popup=1, created=1))
    return redirect(url_for("admin.society_users"))


@bp.route("/users/import-csv", methods=["POST"])
@admin_required
def society_import_users():
    upload = request.files.get("csv_file")
    if not upload or not upload.filename:
        flash("Choose a CSV file to upload.", "error")
        return redirect(url_for("admin.society_users"))

    try:
        raw = upload.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("Could not read CSV as UTF-8.", "error")
        return redirect(url_for("admin.society_users"))

    try:
        rows = list(iter_society_users_from_csv(raw))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.society_users"))

    if not rows:
        flash("No player rows found in CSV.", "error")
        return redirect(url_for("admin.society_users"))

    society = current_user.society
    created = 0
    restored = 0
    updated = 0
    skipped: list[str] = []
    for email_raw, password, friendly_name_raw in rows:
        try:
            email = validate_email_address(email_raw)
        except ValueError:
            skipped.append(f"invalid email {email_raw!r}")
            continue
        try:
            friendly_name = normalize_friendly_name(friendly_name_raw)
        except ValueError as e:
            skipped.append(f"{email}: {e}")
            continue

        existing = User.query.filter_by(email=email).first()
        if existing:
            if existing.society_id != current_user.society_id:
                skipped.append(f"{email}: email used by another society")
                continue
            if not existing.is_deleted:
                if friendly_name is not None:
                    existing.friendly_name = friendly_name
                    updated += 1
                else:
                    skipped.append(f"{email}: already an active player")
                continue
            existing.is_deleted = False
            if friendly_name is not None:
                existing.friendly_name = friendly_name
            try:
                apply_user_password(existing, password or "", society)
            except ValueError as e:
                skipped.append(f"{email}: {e}")
                continue
            restored += 1
            continue

        user = User(
            email=email,
            society_id=current_user.society_id,
            friendly_name=friendly_name,
        )
        try:
            apply_user_password(user, password or "", society)
        except ValueError as e:
            skipped.append(f"{email}: {e}")
            continue
        db.session.add(user)
        created += 1

    db.session.commit()
    msg = f"Import finished: {created} created"
    if updated:
        msg += f", {updated} friendly name(s) updated"
    if restored:
        msg += f", {restored} restored from archive"
    msg += ". Blank passwords use the shared player password."
    if skipped:
        msg += f" Skipped {len(skipped)} row(s): " + "; ".join(skipped[:8])
        if len(skipped) > 8:
            msg += "…"
    flash(msg, "success")
    return redirect(url_for("admin.society_users"))


@bp.route("/users/<int:user_id>/friendly-name", methods=["POST"])
@admin_required
def society_user_update_friendly_name(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.society_id != current_user.society_id:
        flash("That player is not in your society.", "error")
        return redirect(url_for("admin.society_users"))
    try:
        user.friendly_name = normalize_friendly_name(request.form.get("friendly_name", ""))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.society_users"))

    db.session.commit()
    flash(f"Updated friendly name for {user.display_label}.", "success")
    return redirect(url_for("admin.society_users"))


@bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def society_user_reset_password(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.society_id != current_user.society_id:
        flash("That player is not in your society.", "error")
        return redirect(url_for("admin.society_users"))
    if user.is_deleted:
        flash("Restore the player before resetting their password.", "error")
        return redirect(url_for("admin.society_users"))
    if not current_user.society.has_player_password:
        flash("Set a shared player password first.", "error")
        return redirect(url_for("admin.society_users"))

    current_user.society.copy_shared_password_to_user(user)
    db.session.commit()
    flash(
        f"{user.display_label}: personal password reset to the shared player password.",
        "success",
    )
    return redirect(url_for("admin.society_users"))


@bp.route("/users/<int:user_id>/mark-deleted", methods=["POST"])
@admin_required
def society_user_mark_deleted(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.society_id != current_user.society_id:
        flash("That player is not in your society.", "error")
        return redirect(url_for("admin.society_users"))
    if user.is_deleted:
        flash("That player is already marked deleted.", "info")
        return redirect(url_for("admin.society_users"))

    user.is_deleted = True
    db.session.commit()
    flash(f"{user.display_label} marked deleted.", "success")
    return redirect(url_for("admin.society_users"))


@bp.route("/users/<int:user_id>/restore", methods=["POST"])
@admin_required
def society_user_restore(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.society_id != current_user.society_id:
        flash("That player is not in your society.", "error")
        return redirect(url_for("admin.society_users"))
    if not user.is_deleted:
        flash("That player is already active.", "info")
        return redirect(url_for("admin.society_users"))

    user.is_deleted = False
    db.session.commit()
    flash(f"{user.display_label} restored.", "success")
    return redirect(url_for("admin.society_users"))


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def society_user_delete_permanent(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.society_id != current_user.society_id:
        flash("That player is not in your society.", "error")
        return redirect(url_for("admin.society_users"))
    if not user.is_deleted:
        flash("Mark the player deleted before permanently removing them.", "error")
        return redirect(url_for("admin.society_users"))

    label = user.display_label
    Score.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    CompetitionPlayer.query.filter_by(user_id=user.id).delete(
        synchronize_session=False
    )
    db.session.delete(user)
    db.session.commit()
    flash(f"{label} permanently deleted.", "success")
    return redirect(url_for("admin.society_users"))
