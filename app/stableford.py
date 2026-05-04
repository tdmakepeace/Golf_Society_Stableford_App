"""Stableford points from net score vs par (standard 0–5 scale)."""


def strokes_on_hole(playing_handicap: int, stroke_index: int) -> int:
    """
    Extra strokes for this hole from playing handicap.

    Stored stroke index matches the scorecard: **18 = hardest hole** (first spare
    shot from the remainder), **1 = easiest**.

    When ``playing_handicap`` is a multiple of 18 (e.g. 18, 36, 54), there is no
    remainder: every hole gets the same ``base`` strokes and SI does not change
    how those full sets are split (e.g. handicap 18 → 1 shot on every hole).
    """
    if playing_handicap <= 0:
        return 0
    base = playing_handicap // 18
    remainder = playing_handicap % 18
    if remainder == 0:
        return base
    return base + (1 if stroke_index >= 19 - remainder else 0)


def stableford_points_for_hole(par: int, gross: int, strokes_received: int) -> int:
    """
    Net score = gross - strokes_received.
    Points: 5 (3+ under), 4 (2 under), 3 (1 under), 2 (par), 1 (bogey), 0 (double+).
    """
    if gross <= 0:
        return 0
    net = gross - strokes_received
    diff = par - net  # positive = under par
    if diff >= 3:
        return 5
    if diff == 2:
        return 4
    if diff == 1:
        return 3
    if diff == 0:
        return 2
    if diff == -1:
        return 1
    return 0


def total_stableford(
    holes: list[tuple[int, int, int]],
    gross_by_hole: dict[int, int],
    playing_handicap: int,
) -> tuple[int, dict[int, int]]:
    """
    holes: list of (hole_number, par, stroke_index)
    gross_by_hole: hole_number -> gross strokes
    Returns (total_points, hole_points).
    """
    hole_points: dict[int, int] = {}
    total = 0
    for hole_num, par, si in holes:
        g = gross_by_hole.get(hole_num)
        if g is None or g <= 0:
            hole_points[hole_num] = 0
            continue
        recv = strokes_on_hole(playing_handicap, si)
        pts = stableford_points_for_hole(par, g, recv)
        hole_points[hole_num] = pts
        total += pts
    return total, hole_points
