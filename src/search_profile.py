"""
A housing search for one or more people.

Who each person is lives in ``conf/person/<name>.yaml``; what the group is looking
for lives in ``conf/search/<name>.yaml``. Passwords and API keys come only from
environment variables (normally set in ``.env``).
"""

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PERSON_DIR = Path("conf/person")
SEARCH_DIR = Path("conf/search")
DATA_DIR = Path("data")

# Profile attribute -> environment variable holding it (the contact's accounts).
CREDENTIAL_ENV: dict[str, str] = {
    "wohnen_ethz_login": "WOHNEN_ETHZ_LOGIN",
    "wohnen_ethz_password": "WOHNEN_ETHZ_PASSWORD",
    "gmail_login": "GMAIL_ADDRESS",
    "gmail_password": "GMAIL_APP_PASSWORD",
}
API_KEY_ENV: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


class ProfileError(ValueError):
    """
    Raised when a required search field, person or credential is missing.
    """


@dataclass
class Person:
    """
    One person taking part in a search.
    """

    name: str
    description: dict[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        """
        The person's name as written in messages.

        :return: ``description.Name``, or the file name if that is empty.
        """
        return str(self.description.get("Name") or self.name)


class SearchProfile:
    """
    Everything the agent knows about one search.

    A search has one or more ``members``. One of them is the ``contact``: their name,
    phone and email go into contact forms, and their accounts (from the environment)
    are used to log in and send email. Credentials are optional at load time and
    checked with :meth:`require` when a site or provider needs them.
    """

    def __init__(
        self,
        name: str,
        members: Sequence[Person],
        contact: str,
        preferences: Mapping[str, Any],
        data_root: Path = DATA_DIR,
    ) -> None:
        """
        Build a search.

        :param name: Search name; also the folder name under ``data_root``.
        :param members: The people searching together (at least one).
        :param contact: Name of the member who is contacted and whose accounts are used.
        :param preferences: Budget, place and other preferences of the group.
        :param data_root: Root folder for listing records.
        :raises ProfileError: If there are no members, the contact is not a member, or
            ``budget_total`` is not set.
        """
        self.name = name
        self.config_path = SEARCH_DIR / f"{name}.yaml"
        self.data_root = Path(data_root)
        self.members = list(members)
        if not self.members:
            raise ProfileError(
                f"Add at least one person to members in {self.config_path}"
            )
        by_name = {person.name: person for person in self.members}
        if contact not in by_name:
            raise ProfileError(
                f"contact '{contact}' in {self.config_path} must be one of the members"
            )
        self.contact = by_name[contact]

        description = self.contact.description
        self.user_name: str = self.contact.display_name
        self.user_phone_number: str = str(description.get("Phone_number") or "")
        self.user_email: str = str(description.get("Email") or "")

        self.preferences: dict[str, Any] = dict(preferences)
        self.place: str = str(self.preferences.get("place") or "")
        self.place_wg_zimmer: str = str(self.preferences.get("place_wg_zimmer") or "")
        budget = str(self.preferences.get("budget_total") or "").strip()
        if not budget:
            raise ProfileError(f"Set preferences.budget_total in {self.config_path}")
        self.max_rent: int = int(float(budget))

        self.wohnen_ethz_login = ""
        self.wohnen_ethz_password = ""
        self.gmail_login = ""
        self.gmail_password = ""
        for attribute, env_var in CREDENTIAL_ENV.items():
            setattr(self, attribute, os.environ.get(env_var, ""))

    @property
    def data_dir(self) -> Path:
        """
        Folder that holds the per-site records of listings this search has handled.

        :return: ``<data_root>/<name>``.
        """
        return self.data_root / self.name

    @property
    def is_group(self) -> bool:
        """
        Whether more than one person is searching.

        :return: ``True`` for two or more members.
        """
        return len(self.members) > 1

    def require(self, *fields: str) -> None:
        """
        Check that profile attributes are filled in.

        :param fields: Attribute names, for example ``"gmail_login"``.
        :raises ProfileError: If any of them is empty; the message says where to set
            each one.
        """
        missing = [f for f in fields if not getattr(self, f, "")]
        if not missing:
            return
        in_env = [CREDENTIAL_ENV[f] for f in missing if f in CREDENTIAL_ENV]
        in_config = [f for f in missing if f not in CREDENTIAL_ENV]
        parts = []
        if in_env:
            parts.append(f"set {', '.join(in_env)} in .env")
        if in_config:
            parts.append(
                f"fill in {', '.join(in_config)} in {self.config_path} or "
                f"{PERSON_DIR / self.contact.name}.yaml"
            )
        raise ProfileError(f"Search '{self.name}' is incomplete: {'; '.join(parts)}.")

    def api_key(self, provider: str) -> str | None:
        """
        Find the API key for an LLM provider.

        :param provider: One of ``deepseek``, ``claude``, ``openai``.
        :return: The key, or ``None`` if its environment variable is not set.
        """
        return os.environ.get(API_KEY_ENV[provider]) or None

    def description_text(self) -> str:
        """
        Describe the applicant(s) for a prompt.

        :return: One block per person; for a group, a header names the contact.
        """
        if not self.is_group:
            return _render(self.contact.description)
        names = ", ".join(person.display_name for person in self.members)
        blocks = [
            f"{len(self.members)} people searching together: {names}. "
            f"Contact person: {self.contact.display_name}."
        ]
        for person in self.members:
            blocks.append(f"## {person.display_name}\n{_render(person.description)}")
        return "\n\n".join(blocks)

    def preferences_text(self) -> str:
        """
        Render the search preferences for a prompt.

        :return: Non-empty preference fields as ``key: value`` lines, plus the
            number of people.
        """
        return f"people: {len(self.members)}\n{_render(self.preferences)}"


def _render(data: Mapping[str, Any]) -> str:
    """
    Turn a flat mapping into ``key: value`` lines, skipping empty values.

    :param data: Mapping to render.
    :return: One line per non-empty field.
    """
    return "\n".join(f"{key}: {value}" for key, value in data.items() if value)
