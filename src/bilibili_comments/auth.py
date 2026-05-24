"""Load Bilibili API credentials from a JSON file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bilibili_api import Credential

# Project root: Scraping/
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CREDENTIALS_PATH = _PROJECT_ROOT / "credentials.json"

_REQUIRED_KEYS = ("sessdata", "bili_jct", "buvid3")

# JSON key aliases (case-insensitive match on normalized name).
_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "sessdata": ("SESSDATA", "sessdata"),
    "bili_jct": ("bili_jct", "BILI_JCT"),
    "buvid3": ("buvid3", "BUVID3"),
    "dedeuserid": ("DEDEUSERID", "dedeuserid", "DedeUserID"),
    "ac_time_value": ("AC_TIME_VALUE", "ac_time_value"),
}


def _normalize_key(key: str) -> str:
    return key.strip().lower()


def _lookup(data: dict[str, Any], canonical: str) -> str | None:
    """Return the first non-empty value for a canonical field name."""
    aliases = _KEY_ALIASES.get(canonical, (canonical,))
    alias_set = {a.lower() for a in aliases}
    for raw_key, value in data.items():
        if _normalize_key(raw_key) in alias_set:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
    return None


def load_credentials(path: Path | str | None = None) -> dict[str, str]:
    """
    Read cookie fields from ``credentials.json``.

    Required keys: SESSDATA, bili_jct, buvid3 (any common alias accepted).
    Optional: dedeuserid, ac_time_value — included only when present and non-empty.
    """
    cred_path = Path(path) if path is not None else DEFAULT_CREDENTIALS_PATH
    if not cred_path.is_file():
        raise FileNotFoundError(
            f"Credentials file not found: {cred_path}\n"
            f"Copy credentials.json.example to credentials.json and fill in your cookies."
        )

    try:
        raw = json.loads(cred_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {cred_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"Expected a JSON object in {cred_path}, got {type(raw).__name__}")

    result: dict[str, str] = {}
    missing: list[str] = []
    for key in _REQUIRED_KEYS:
        value = _lookup(raw, key)
        if value is None:
            missing.append(key)
        else:
            result[key] = value

    if missing:
        raise ValueError(
            f"Missing required credential field(s) in {cred_path}: {', '.join(missing)}"
        )

    for optional in ("dedeuserid", "ac_time_value"):
        value = _lookup(raw, optional)
        if value is not None:
            result[optional] = value

    return result


def load_credential(path: Path | str | None = None) -> Credential:
    """
    Build a ``bilibili_api.Credential`` from ``credentials.json``.

    Only sessdata, bili_jct, and buvid3 are required. ``ac_time_value`` is never
    required; it is passed through only if explicitly set in the JSON file.
    """
    data = load_credentials(path)
    kwargs: dict[str, str] = {
        "sessdata": data["sessdata"],
        "bili_jct": data["bili_jct"],
        "buvid3": data["buvid3"],
    }
    if "dedeuserid" in data:
        kwargs["dedeuserid"] = data["dedeuserid"]
    if "ac_time_value" in data:
        kwargs["ac_time_value"] = data["ac_time_value"]

    return Credential(**kwargs)


if __name__ == "__main__":
    cred = load_credential()
    print("Loaded credential:")
    print(f"  sessdata:   {'yes' if cred.has_sessdata() else 'no'}")
    print(f"  bili_jct:   {'yes' if cred.has_bili_jct() else 'no'}")
    print(f"  buvid3:     {'yes' if cred.has_buvid3() else 'no'}")
    print(f"  ac_time_value: {'yes' if cred.has_ac_time_value() else 'no (not required)'}")
