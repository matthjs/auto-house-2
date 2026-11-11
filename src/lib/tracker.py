"""
Per-listing records of what the agent did, stored as JSON next to the profile.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUSES = ("skipped", "drafted", "needs_review", "failed", "rejected", "sent")
# Listings with these statuses are never processed again.
FINAL_STATUSES = frozenset({"skipped", "rejected", "sent"})
LEGACY_STATUS = "sent"


def now() -> str:
    """
    Current UTC time as an ISO 8601 string.

    :return: For example ``2026-11-11T18:15:00+00:00``.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_id(listing_id: str) -> str:
    """
    Make a listing id safe to use as a file name.

    :param listing_id: Id taken from the listing URL.
    :return: The id with path separators replaced.
    """
    return listing_id.replace("/", "_").replace("\\", "_")


class Tracker:
    """
    Read and write the record of each listing on one site.

    Records live in ``secret/<name>/data/<site>/<listing id>.json``. Files written by
    the earlier version of this project have no ``status`` field; they are treated
    as ``sent`` so those listings are never contacted twice. File names starting
    with ``_`` are working files, not records.
    """

    def __init__(self, data_dir: Path, site: str) -> None:
        """
        Open (and create if needed) the folder for one site.

        :param data_dir: The profile's data folder.
        :param site: Site folder name, for example ``flatfox.ch``.
        """
        self.directory = Path(data_dir) / site
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, listing_id: str) -> Path:
        """
        File that holds a listing's record.

        :param listing_id: Listing id.
        :return: Path of the JSON file (it may not exist yet).
        """
        return self.directory / f"{safe_id(listing_id)}.json"

    def get(self, listing_id: str) -> dict[str, Any] | None:
        """
        Load a listing's record.

        :param listing_id: Listing id.
        :return: The record with ``status`` filled in, or ``None`` if there is none.
        """
        path = self.path(listing_id)
        if not path.is_file():
            return None
        with path.open(encoding="utf-8") as f:
            record = json.load(f)
        record.setdefault("status", LEGACY_STATUS)
        return record

    def is_done(self, listing_id: str) -> bool:
        """
        Whether a listing was already handled for good.

        :param listing_id: Listing id.
        :return: ``True`` if its status is in :data:`FINAL_STATUSES`.
        """
        record = self.get(listing_id)
        return record is not None and record["status"] in FINAL_STATUSES

    def save(self, listing_id: str, status: str, **fields: Any) -> dict[str, Any]:
        """
        Create or update a listing's record.

        New fields are merged into the existing record, ``updated_at`` is refreshed
        and the status change is appended to ``history``.

        :param listing_id: Listing id.
        :param status: New status; one of :data:`STATUSES`.
        :param fields: Other fields to store, for example ``url`` or ``subject``.
        :return: The saved record.
        :raises ValueError: If ``status`` is unknown.
        """
        if status not in STATUSES:
            raise ValueError(f"Unknown status '{status}'")
        timestamp = now()
        record = self.get(listing_id) or {"id": listing_id, "created_at": timestamp}
        record.update(fields)
        record["status"] = status
        record["updated_at"] = timestamp
        record.setdefault("history", []).append({"status": status, "at": timestamp})
        self._write(self.path(listing_id), record)
        return record

    def records(self) -> list[dict[str, Any]]:
        """
        Load every record on this site.

        :return: Records sorted by last update, newest first.
        """
        records = []
        for path in self.directory.glob("*.json"):
            if path.name.startswith("_"):
                continue
            record = self.get(path.stem)
            if record is not None:
                records.append(record)
        return sorted(records, key=lambda r: r.get("updated_at", ""), reverse=True)

    def write_working_file(self, name: str, content: dict[str, Any]) -> Path:
        """
        Write a file for the user to edit, such as a draft under review.

        :param name: File name without ``.json``; a leading ``_`` is added.
        :param content: JSON content.
        :return: Path of the written file.
        """
        path = self.directory / f"_{name}.json"
        self._write(path, content)
        return path

    def read_working_file(self, name: str, delete: bool = True) -> dict[str, Any]:
        """
        Read back a file written by :meth:`write_working_file`.

        :param name: Same name as given to :meth:`write_working_file`.
        :param delete: Remove the file after reading it.
        :return: The file's JSON content.
        """
        path = self.directory / f"_{name}.json"
        with path.open(encoding="utf-8") as f:
            content = json.load(f)
        if delete:
            path.unlink()
        return content

    @staticmethod
    def _write(path: Path, content: dict[str, Any]) -> None:
        """
        Write JSON atomically, so a crash never leaves a half-written record.

        :param path: Destination file.
        :param content: JSON content.
        """
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
