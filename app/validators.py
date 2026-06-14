import re

from email_validator import EmailNotValidError, validate_email


def validate_email_address(raw: str) -> str:
    """Return normalized email or raise ValueError."""
    if not raw or not raw.strip():
        raise ValueError("Email is required.")
    try:
        info = validate_email(raw.strip(), check_deliverability=False)
        return info.normalized
    except EmailNotValidError as e:
        raise ValueError(str(e)) from e


def validate_password(password: str) -> None:
    """
    Min 8 chars, at least one digit, one letter, one upper, one lower, one symbol.
    """
    if not password:
        raise ValueError("Password is required.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one number.")
    if not re.search(r"[A-Za-z]", password):
        raise ValueError("Password must contain at least one letter.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must contain at least one symbol.")


def validate_bulk_event_password(password: str) -> None:
    """
    Relaxed rule for competition passwords (e.g. event date).
    Minimum 8 characters; any characters allowed.
    """
    if not password:
        raise ValueError("Password is required.")
    if len(password) < 8:
        raise ValueError(
            "Password must be at least 8 characters (e.g. 20260503 or SpringOuting26)."
        )


validate_competition_password = validate_bulk_event_password


def normalize_friendly_name(raw: str | None) -> str | None:
    """Return stripped friendly name, or None if blank."""
    if raw is None:
        return None
    name = raw.strip()
    if not name:
        return None
    if len(name) > 120:
        raise ValueError("Friendly name must be 120 characters or fewer.")
    return name


def normalize_registration_base_url(raw: str | None) -> str | None:
    """Return normalized public base URL for registration links, or None if blank."""
    if raw is None:
        return None
    url = raw.strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://.")
    return url.rstrip("/")
