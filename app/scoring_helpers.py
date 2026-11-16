from __future__ import annotations

from . import db
from .models import Competition, CompetitionPlayer, Hole, Score, User
from .stableford import strokes_on_hole, total_stableford

# Blank holes count as this many shots in the displayed round total.
UNSCORED_HOLE_STROKES = 10


def gross_total_label(entered: int, holes_scored: int, hole_count: int) -> str:
    """
    Shots actually entered, plus 10 for each unscored hole.

    14 holes totalling 82, with 4 blanks, displays as ``82(+40, 122)``.
    A complete card shows only the entered total. A card with no scores shows an em dash.
    """
    if holes_scored <= 0:
        return "—"
    missing = hole_count - holes_scored
    if missing <= 0:
        return str(entered)
    added = missing * UNSCORED_HOLE_STROKES
    return f"{entered}(+{added}, {entered + added})"


def course_hole_tuples(course) -> list[tuple[int, int, int]]:
    holes = (
        Hole.query.filter_by(course_id=course.id)
        .order_by(Hole.hole_number)
        .all()
    )
    return [(h.hole_number, h.par, h.stroke_index) for h in holes]


def _apply_hole_score(comp: Competition, user: User, hole_number: int, raw: str) -> str | None:
    if raw == "":
        Score.query.filter_by(
            competition_id=comp.id,
            user_id=user.id,
            hole_number=hole_number,
        ).delete(synchronize_session=False)
        return None
    try:
        strokes = int(raw)
    except ValueError:
        return f"Hole {hole_number}: invalid strokes."
    if strokes < 1 or strokes > 20:
        return f"Hole {hole_number}: strokes must be 1–20."
    score = Score.query.filter_by(
        competition_id=comp.id,
        user_id=user.id,
        hole_number=hole_number,
    ).first()
    if score:
        score.gross_strokes = strokes
    else:
        db.session.add(
            Score(
                competition_id=comp.id,
                user_id=user.id,
                hole_number=hole_number,
                gross_strokes=strokes,
            )
        )
    return None


def save_competition_scores(
    comp: Competition, user: User, holes: list, form_data
) -> str | None:
    """
    Persist gross scores from a form mapping (hole inputs as strokes_N).
    A blank field clears that hole. Returns an error message, or None on
    success (caller should commit).
    """
    for h in holes:
        err = _apply_hole_score(
            comp,
            user,
            h.hole_number,
            form_data.get(f"strokes_{h.hole_number}", "").strip(),
        )
        if err:
            return err
    return None


def save_submitted_hole_scores(
    comp: Competition, user: User, holes: list, form_data
) -> str | None:
    """
    Persist only holes whose strokes_N field was submitted.
    Used by match mode so saving one hole does not clear the rest of the card.
    """
    for h in holes:
        key = f"strokes_{h.hole_number}"
        if key not in form_data:
            continue
        err = _apply_hole_score(comp, user, h.hole_number, form_data.get(key, "").strip())
        if err:
            return err
    return None


def player_result(comp: Competition, user: User) -> dict:
    entry = CompetitionPlayer.query.filter_by(
        competition_id=comp.id, user_id=user.id
    ).first()
    if not entry:
        return {
            "playing_handicap": 0,
            "total_points": 0,
            "hole_points": {},
            "gross_by_hole": {},
            "holes": [],
            "rows": [],
            "course_par_total": 0,
            "gross_total": None,
            "gross_display": "—",
            "target_gross_total": 0,
            "holes_entered": 0,
        }

    hole_rows = (
        Hole.query.filter_by(course_id=comp.course_id)
        .order_by(Hole.hole_number)
        .all()
    )
    holes = [(h.hole_number, h.par, h.stroke_index) for h in hole_rows]
    scores = Score.query.filter_by(competition_id=comp.id, user_id=user.id).all()
    gross = {s.hole_number: s.gross_strokes for s in scores}
    total_pts, hole_pts = total_stableford(holes, gross, entry.playing_handicap)

    rows = []
    course_par_total = 0
    gross_sum = 0
    holes_with_scores = 0
    for h in hole_rows:
        course_par_total += h.par
        g = gross.get(h.hole_number)
        recv = strokes_on_hole(entry.playing_handicap, h.stroke_index)
        pts = hole_pts.get(h.hole_number, 0)
        net_par_gross = h.par + recv
        net_strokes = (g - recv) if g is not None else None
        if g is not None:
            gross_sum += g
            holes_with_scores += 1
        rows.append(
            {
                "hole": h.hole_number,
                "par": h.par,
                "distance": h.distance,
                "stroke_index": h.stroke_index,
                "strokes_received": recv,
                "net_par_gross": net_par_gross,
                "gross": g,
                "net_strokes": net_strokes,
                "points": pts,
            }
        )

    target_gross_total = course_par_total + entry.playing_handicap
    return {
        "playing_handicap": entry.playing_handicap,
        "total_points": total_pts,
        "hole_points": hole_pts,
        "gross_by_hole": gross,
        "rows": rows,
        "course_par_total": course_par_total,
        "gross_total": gross_sum if holes_with_scores else None,
        "gross_display": gross_total_label(
            gross_sum, holes_with_scores, len(hole_rows)
        ),
        "target_gross_total": target_gross_total,
        "holes_entered": holes_with_scores,
    }


def competition_leaderboard(comp: Competition) -> list[dict]:
    holes = course_hole_tuples(comp.course)
    out: list[dict] = []
    for entry in CompetitionPlayer.query.filter_by(competition_id=comp.id).all():
        user = entry.user
        scores = Score.query.filter_by(competition_id=comp.id, user_id=user.id).all()
        gross = {s.hole_number: s.gross_strokes for s in scores}
        total_pts, hole_pts = total_stableford(holes, gross, entry.playing_handicap)
        gross_sum = sum(gross[n] for n, _, _ in holes if n in gross)
        holes_scored = sum(1 for n, _, _ in holes if n in gross)
        gross_total = gross_sum if holes_scored else None
        user_par_by_hole: dict[int, int] = {}
        user_par_total = 0
        for hole_num, par, si in holes:
            recv = strokes_on_hole(entry.playing_handicap, si)
            playing_par = par + recv
            user_par_by_hole[hole_num] = playing_par
            user_par_total += playing_par
        out.append(
            {
                "user_id": user.id,
                "email": user.email,
                "display_label": user.display_label,
                "playing_handicap": entry.playing_handicap,
                "total_points": total_pts,
                "gross_total": gross_total,
                "gross_display": gross_total_label(gross_sum, holes_scored, len(holes)),
                "hole_points": hole_pts,
                "gross_by_hole": gross,
                "user_par_by_hole": user_par_by_hole,
                "user_par_total": user_par_total,
            }
        )
    out.sort(key=lambda r: r["total_points"], reverse=True)
    return out
