from __future__ import annotations

from .models import Competition, CompetitionPlayer, Hole, Score, User
from .stableford import strokes_on_hole, total_stableford


def course_hole_tuples(course) -> list[tuple[int, int, int]]:
    holes = (
        Hole.query.filter_by(course_id=course.id)
        .order_by(Hole.hole_number)
        .all()
    )
    return [(h.hole_number, h.par, h.stroke_index) for h in holes]


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
            "target_gross_total": 0,
            "holes_entered": 0,
        }

    holes = course_hole_tuples(comp.course)
    scores = Score.query.filter_by(competition_id=comp.id, user_id=user.id).all()
    gross = {s.hole_number: s.gross_strokes for s in scores}
    total_pts, hole_pts = total_stableford(holes, gross, entry.playing_handicap)

    rows = []
    course_par_total = 0
    gross_sum = 0
    for hole_num, par, si in holes:
        course_par_total += par
        g = gross.get(hole_num)
        recv = strokes_on_hole(entry.playing_handicap, si)
        pts = hole_pts.get(hole_num, 0)
        net_par_gross = par + recv
        net_strokes = (g - recv) if g is not None else None
        if g is not None:
            gross_sum += g
        rows.append(
            {
                "hole": hole_num,
                "par": par,
                "stroke_index": si,
                "strokes_received": recv,
                "net_par_gross": net_par_gross,
                "gross": g,
                "net_strokes": net_strokes,
                "points": pts,
            }
        )

    holes_with_scores = len(gross)
    target_gross_total = course_par_total + entry.playing_handicap
    return {
        "playing_handicap": entry.playing_handicap,
        "total_points": total_pts,
        "hole_points": hole_pts,
        "gross_by_hole": gross,
        "rows": rows,
        "course_par_total": course_par_total,
        "gross_total": gross_sum if holes_with_scores else None,
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
        gross_total = sum(gross.values()) if gross else None
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
                "playing_handicap": entry.playing_handicap,
                "total_points": total_pts,
                "gross_total": gross_total,
                "hole_points": hole_pts,
                "gross_by_hole": gross,
                "user_par_by_hole": user_par_by_hole,
                "user_par_total": user_par_total,
            }
        )
    out.sort(key=lambda r: r["total_points"], reverse=True)
    return out
