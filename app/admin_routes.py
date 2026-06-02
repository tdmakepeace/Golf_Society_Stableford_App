from __future__ import annotations

from flask import Blueprint, flash, make_response, redirect, render_template, request, url_for
from sqlalchemy import or_
from flask_login import current_user, login_user, logout_user

from . import db
from .csv_players import iter_players_from_csv
from .decorators import admin_required
from .models import Admin, Competition, CompetitionPlayer, Course, Hole, Score, Society, User
from .scoring_helpers import competition_leaderboard
from .validators import (
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
        competitions=comps,
    )


@bp.route("/courses/new", methods=["GET", "POST"])
@admin_required
def course_new():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        postcode = (request.form.get("postcode") or "").strip()
        if not name:
            flash("Course name is required.", "error")
            return render_template("admin/course_form.html", course=None, holes=[])

        pars = []
        sis = []
        for i in range(1, 19):
            try:
                p = int(request.form.get(f"par_{i}", "4"))
                si = int(request.form.get(f"si_{i}", str(i)))
            except (TypeError, ValueError):
                flash("Invalid par or stroke index.", "error")
                return render_template("admin/course_form.html", course=None, holes=[])
            if p < 3 or p > 6:
                flash(f"Hole {i}: par must be between 3 and 6.", "error")
                return render_template("admin/course_form.html", course=None, holes=[])
            if si < 1 or si > 18:
                flash(f"Hole {i}: stroke index must be 1–18.", "error")
                return render_template("admin/course_form.html", course=None, holes=[])
            pars.append(p)
            sis.append(si)

        if len(set(sis)) != 18:
            flash("Stroke indexes must be unique 1–18 across all holes.", "error")
            return render_template("admin/course_form.html", course=None, holes=[])

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
            return render_template("admin/course_form.html", course=c, holes=holes)

        pars = []
        sis = []
        for i in range(1, 19):
            try:
                p = int(request.form.get(f"par_{i}", "4"))
                si = int(request.form.get(f"si_{i}", str(i)))
            except (TypeError, ValueError):
                flash("Invalid par or stroke index.", "error")
                return render_template("admin/course_form.html", course=c, holes=holes)
            if p < 3 or p > 6:
                flash(f"Hole {i}: par must be between 3 and 6.", "error")
                return render_template("admin/course_form.html", course=c, holes=holes)
            if si < 1 or si > 18:
                flash(f"Hole {i}: stroke index must be 1–18.", "error")
                return render_template("admin/course_form.html", course=c, holes=holes)
            pars.append(p)
            sis.append(si)

        if len(set(sis)) != 18:
            flash("Stroke indexes must be unique 1–18 across all holes.", "error")
            return render_template("admin/course_form.html", course=c, holes=holes)

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
            "That player is not in this society yet. Add them under Society players first.",
            "error",
        )
        return redirect(url_for("admin.society_users"))

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
    flash(f"Updated handicap for {entry.user.email}.", "success")
    return redirect(url_for("admin.competition_detail", comp_id=comp.id))


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
        society=current_user.society,
    )


@bp.route("/users/new", methods=["POST"])
@admin_required
def society_user_new():
    email_raw = request.form.get("email", "")
    password = request.form.get("password", "")
    try:
        email = validate_email_address(email_raw)
        validate_password(password)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.society_users"))

    existing_any = User.query.filter_by(email=email).first()
    if existing_any:
        flash("That email is already in use.", "error")
        return redirect(url_for("admin.society_users"))

    user = User(email=email, society_id=current_user.society_id)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash("Society player created.", "success")
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
    flash(f"{user.email} marked deleted.", "success")
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
    flash(f"{user.email} restored.", "success")
    return redirect(url_for("admin.society_users"))
