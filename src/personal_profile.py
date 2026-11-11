"""
A user's profile: description and living preferences from ``conf/profile/<name>.yaml``,
passwords and API keys from environment variables (normally set in ``.env``).
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PROFILE_DIR = Path("conf/profile")
DATA_DIR = Path("data")

# Profile attribute -> environment variable holding it.
CREDENTIAL_ENV: dict[str, str] = {
    "wohnen_ethz_login": "WOHNEN_ETHZ_LOGIN",
    "wohnen_ethz_password": "WOHNEN_ETHZ_PASSWORD",
    "flatfox_login": "FLATFOX_LOGIN",
    "flatfox_password": "FLATFOX_PASSWORD",
    "gmail_login": "GMAIL_ADDRESS",
    "gmail_password": "GMAIL_APP_PASSWORD",
    "gmail_login2": "CODE_INBOX_ADDRESS",
    "gmail_password2": "CODE_INBOX_APP_PASSWORD",
}
API_KEY_ENV: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}


class ProfileError(ValueError):
    """
    Raised when a required profile field or credential is empty.
    """


class PersonalProfile:
    """
    Everything the agent knows about one user.

    ``description`` (who the user is) and ``preferences`` (what they are looking for)
    come from the user's profile config. Logins, passwords and API keys come only
    from environment variables (see :data:`CREDENTIAL_ENV` and :data:`API_KEY_ENV`).
    Credentials are optional at load time and checked with :meth:`require` when a
    site or provider needs them.
    """

    def __init__(
        self,
        name: str,
        description: Mapping[str, Any],
        preferences: Mapping[str, Any],
        data_root: Path = DATA_DIR,
    ) -> None:
        """
        Build a profile.

        :param name: Profile name; also the folder name under ``data_root``.
        :param description: Facts about the user, used in every message.
        :param preferences: Budget, place and other search preferences.
        :param data_root: Root folder for listing records.
        :raises ProfileError: If ``budget_upper_bound`` is not set.
        """
        self.name = name
        self.config_path = PROFILE_DIR / f"{name}.yaml"
        self.data_root = Path(data_root)

        self.description: dict[str, Any] = dict(description)
        self.user_name: str = str(self.description.get("Name") or "")
        self.user_phone_number: str = str(self.description.get("Phone_number") or "")
        self.user_email: str = str(self.description.get("Email") or "")

        self.preferences: dict[str, Any] = dict(preferences)
        self.place: str = str(self.preferences.get("place") or "")
        self.place_wg_zimmer: str = str(self.preferences.get("place_wg_zimmer") or "")
        budget = str(self.preferences.get("budget_upper_bound") or "").strip()
        if not budget:
            raise ProfileError(
                f"Set preferences.budget_upper_bound in {self.config_path}"
            )
        self.max_rent: int = int(float(budget))
        # wgzimmer.ch only offers its price filter in steps of 50.
        self.max_rent_wg_zimmer: int = (self.max_rent + 49) // 50 * 50

        self.wohnen_ethz_login = ""
        self.wohnen_ethz_password = ""
        self.flatfox_login = ""
        self.flatfox_password = ""
        self.gmail_login = ""
        self.gmail_password = ""
        self.gmail_login2 = ""
        self.gmail_password2 = ""
        for attribute, env_var in CREDENTIAL_ENV.items():
            setattr(self, attribute, os.environ.get(env_var, ""))

    @property
    def data_dir(self) -> Path:
        """
        Folder that holds the per-site records of listings this user has handled.

        :return: ``<data_root>/<name>``.
        """
        return self.data_root / self.name

    def require(self, *fields: str) -> None:
        """
        Check that profile attributes are filled in.

        :param fields: Attribute names, for example ``"flatfox_login"``.
        :raises ProfileError: If any of them is empty; the message says where to set
            each one.
        """
        missing = [field for field in fields if not getattr(self, field, "")]
        if not missing:
            return
        in_env = [CREDENTIAL_ENV[f] for f in missing if f in CREDENTIAL_ENV]
        in_config = [f for f in missing if f not in CREDENTIAL_ENV]
        parts = []
        if in_env:
            parts.append(f"set {', '.join(in_env)} in .env")
        if in_config:
            parts.append(f"fill in {', '.join(in_config)} in {self.config_path}")
        raise ProfileError(f"Profile '{self.name}' is incomplete: {'; '.join(parts)}.")

    def api_key(self, provider: str) -> str | None:
        """
        Find the API key for an LLM provider.

        :param provider: One of ``deepseek``, ``openai``, ``claude``.
        :return: The key, or ``None`` if its environment variable is not set.
        """
        return os.environ.get(API_KEY_ENV[provider]) or None

    def description_text(self) -> str:
        """
        Render the user's description for a prompt.

        :return: Non-empty description fields as ``key: value`` lines.
        """
        return _render(self.description)

    def preferences_text(self) -> str:
        """
        Render the user's living preferences for a prompt.

        :return: Non-empty preference fields as ``key: value`` lines.
        """
        return _render(self.preferences)


def _render(data: Mapping[str, Any]) -> str:
    """
    Turn a flat mapping into ``key: value`` lines, skipping empty values.

    :param data: Mapping to render.
    :return: One line per non-empty field.
    """
    return "\n".join(f"{key}: {value}" for key, value in data.items() if value)
