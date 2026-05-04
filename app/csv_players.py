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


def iter_players_from_csv(content: str) -> Iterator[tuple[str, int]]:
    """
    Yield (email, playing_handicap) from CSV text.
    Accepts header aliases: email / e_mail / mail; handicap / playing_handicap / hcp / playing_hc.
    Skips empty rows.
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
        hcp_s = (
            d.get("handicap")
            or d.get("playing_handicap")
            or d.get("hcp")
            or d.get("playing_hc")
            or d.get("handicap_index")
            or "0"
        )
        try:
            hcp = int(float(hcp_s))
        except ValueError as e:
            raise ValueError(f"Invalid handicap for {email!r}: {hcp_s!r}.") from e
        yield email, hcp
