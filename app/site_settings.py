from __future__ import annotations

from flask import url_for

from .models import AppSetting

REGISTRATION_BASE_URL_KEY = "registration_base_url"


def get_registration_base_url() -> str | None:
    return AppSetting.get_value(REGISTRATION_BASE_URL_KEY)


def set_registration_base_url(url: str | None) -> None:
    AppSetting.set_value(REGISTRATION_BASE_URL_KEY, url)


def player_registration_url(token: str) -> str:
    """Full player self-registration URL for a society token."""
    path = url_for("user.register", token=token, _external=False)
    base = get_registration_base_url()
    if base:
        return f"{base}{path}"
    return url_for("user.register", token=token, _external=True)
