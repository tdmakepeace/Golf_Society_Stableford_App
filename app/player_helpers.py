from __future__ import annotations

from .models import Society, User
from .validators import validate_password


def apply_user_password(user: User, password: str, society: Society) -> None:
    """Set personal password from form/CSV, or copy society shared password hash."""
    pw = (password or "").strip()
    if pw:
        validate_password(pw)
        user.set_password(pw)
    else:
        if not society.has_player_password:
            raise ValueError(
                "Set a shared player password first, or provide an initial personal password."
            )
        society.copy_shared_password_to_user(user)
