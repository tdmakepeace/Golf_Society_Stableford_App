from __future__ import annotations

import csv
import io
from typing import Iterator


def _norm(name: str) -> str:
    return (
        name.replace("\ufeff", "")
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def iter_society_users_from_csv(content: str) -> Iterator[tuple[str, str | None]]:
    """
    Yield (email, password_or_none) from CSV text.
    Accepts header aliases: email / e_mail / mail; password / pwd / pass.
    Empty password cell means use the society shared password.
    """
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError("The CSV file must include a header row.")

    for raw in reader:
        d = {_norm(k): (v or "").strip() for k, v in raw.items() if k}
        email = (
            d.get("email")
            or d.get("e_mail")
            or d.get("mail")
            or d.get("player_email")
        )
        if not email:
            continue
        password = d.get("password") or d.get("pwd") or d.get("pass") or None
        if password == "":
            password = None
        yield email, password


def parse_course_holes_from_csv(content: str) -> list[tuple[int, int, int]]:
    """
    Parse CSV with hole, par, and stroke index columns.
    Returns sorted list of (hole_number, par, stroke_index) for holes 1–18.
    """
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError("The CSV file must include a header row.")

    holes: dict[int, tuple[int, int]] = {}
    for raw in reader:
        d = {_norm(k): (v or "").strip() for k, v in raw.items() if k}
        hole_s = d.get("hole") or d.get("hole_number") or d.get("no") or d.get("#")
        par_s = d.get("par")
        si_s = (
            d.get("si")
            or d.get("stroke_index")
            or d.get("strokeindex")
            or d.get("index")
        )
        if not hole_s or not par_s or not si_s:
            continue
        try:
            hole_num = int(float(hole_s))
            par = int(float(par_s))
            si = int(float(si_s))
        except ValueError as e:
            raise ValueError(
                f"Invalid hole data (hole={hole_s!r}, par={par_s!r}, si={si_s!r})."
            ) from e
        if hole_num < 1 or hole_num > 18:
            raise ValueError(f"Hole number must be 1–18, got {hole_num}.")
        if par < 3 or par > 6:
            raise ValueError(f"Hole {hole_num}: par must be between 3 and 6.")
        if si < 1 or si > 18:
            raise ValueError(f"Hole {hole_num}: stroke index must be 1–18.")
        if hole_num in holes:
            raise ValueError(f"Duplicate hole number {hole_num} in CSV.")
        holes[hole_num] = (par, si)

    if len(holes) != 18:
        missing = sorted(set(range(1, 19)) - set(holes.keys()))
        raise ValueError(
            f"CSV must define all 18 holes; missing hole(s): {', '.join(map(str, missing))}."
        )

    sis = [holes[i][1] for i in range(1, 19)]
    if len(set(sis)) != 18:
        raise ValueError("Stroke indexes must be unique 1–18 across all holes.")

    return [(i, holes[i][0], holes[i][1]) for i in range(1, 19)]
