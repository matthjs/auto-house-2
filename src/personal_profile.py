"""
Load a user's description, living preferences and credentials from ``secret/<name>/``.
"""

import json
import os
from pathlib import Path
from typing import Any

SECRET_DIR = Path("secret")

API_KEY_SOURCES: dict[str, tuple[str, tuple[str, ...]]] = {
    "deepseek": ("DeepSeek_API_KEY", ("DEEPSEEK_API_KEY",)),
    "openai": ("OpenAI_API_KEY", ("OPENAI_API_KEY",)),
    "claude": ("Anthropic_API_KEY", ("ANTHROPIC_API_KEY",)),
}


class ProfileError(ValueError):
    """
    Raised when a profile file is missing or a required field is empty.
    """


def _load_json(path: Path) -> dict[str, Any]:
    """
    Read one JSON file of a profile.

    :param path: File to read.
    :return: The parsed JSON object.
    :raises ProfileError: If the file does not exist.
    """
    if not path.is_file():
        raise ProfileError(
            f"Missing {path}. Copy secret/example/ to secret/<name>/ and fill it in."
        )
    with path.open(encoding="utf-8") as f:
        return json.load(f)


class PersonalProfile:
    """
    Everything the agent knows about one user.

    Reads three files from ``secret/<name>/``: ``my_description.json`` (who the user
    is), ``living_preferences.json`` (what they are looking for) and
    ``site_credentials.json`` (logins and API keys). Credentials are optional at load
    time and checked with :meth:`require` when a site or provider needs them.
    """

    def __init__(self, name: str, secret_dir: Path = SECRET_DIR) -> None:
        """
        Load a profile from disk.

        :param name: Folder name under ``secret_dir``.
        :param secret_dir: Root folder that holds all profiles.
        :raises ProfileError: If a file is missing or a required field is empty.
        """
        self.name = name
        self.directory = Path(secret_dir) / name

        description = _load_json(self.directory / "my_description.json")
        self.description: dict[str, Any] = description
        self.user_name: str = description.get("Name", "")
        self.user_phone_number: str = description.get("Phone_number", "")
        self.user_email: str = description.get("Email", "")

        preferences = _load_json(self.directory / "living_preferences.json")
        self.preferences: dict[str, Any] = preferences
        self.place: str = preferences.get("place", "")
        self.place_wg_zimmer: str = preferences.get("place_wg_zimmer", "")
        budget = str(preferences.get("budget_upper_bound", "")).strip()
        if not budget:
            raise ProfileError(
                f"Set 'budget_upper_bound' in {self.directory}/living_preferences.json"
            )
        self.max_rent: int = int(float(budget))
        # wgzimmer.ch only offers its price filter in steps of 50.
        self.max_rent_wg_zimmer: int = (self.max_rent + 49) // 50 * 50

        credentials = _load_json(self.directory / "site_credentials.json")
        self.credentials: dict[str, str] = credentials
        self.wohnen_ethz_login: str = credentials.get("wohnen_ethz_login", "")
        self.wohnen_ethz_password: str = credentials.get("wohnen_ethz_password", "")
        self.flatfox_login: str = credentials.get("flatfox_login", "")
        self.flatfox_password: str = credentials.get("flatfox_password", "")
        self.gmail_login: str = credentials.get("login", "")
        self.gmail_password: str = credentials.get("password", "")
        self.gmail_login2: str = credentials.get("login2", "")
        self.gmail_password2: str = credentials.get("password2", "")

    @property
    def data_dir(self) -> Path:
        """
        Folder that holds the per-site records of listings this user has handled.

        :return: ``secret/<name>/data``.
        """
        return self.directory / "data"

    def require(self, *fields: str) -> None:
        """
        Check that profile attributes are filled in.

        :param fields: Attribute names, for example ``"flatfox_login"``.
        :raises ProfileError: If any of them is empty.
        """
        missing = [field for field in fields if not getattr(self, field, "")]
        if missing:
            raise ProfileError(
                f"Profile '{self.name}' is missing: {', '.join(missing)}. "
                f"Fill them in under {self.directory}/."
            )

    def api_key(self, provider: str) -> str | None:
        """
        Find the API key for an LLM provider.

        Environment variables win over ``site_credentials.json``.

        :param provider: One of ``deepseek``, ``openai``, ``claude``.
        :return: The key, or ``None`` if none is set.
        """
        json_key, env_vars = API_KEY_SOURCES[provider]
        for env_var in env_vars:
            if os.environ.get(env_var):
                return os.environ[env_var]
        return self.credentials.get(json_key) or None

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


def _render(data: dict[str, Any]) -> str:
    """
    Turn a flat dict into ``key: value`` lines, skipping empty values.

    :param data: Dict to render.
    :return: One line per non-empty field.
    """
    return "\n".join(f"{key}: {value}" for key, value in data.items() if value)
