"""Jev local contacts book.

Maps spoken names to phone numbers for WhatsApp deep links. Stored as
plain JSON at ~/.jev/contacts.json so Aarya can edit it by hand:

    {"mom": "+919876543210", "best friend": "+911234567890"}

Phone numbers must be in international format without spaces or dashes.
"""

from __future__ import annotations

import json
import re

from app.services.jev.paths import jev_file
from app.services.tools.base import ToolError

_CONTACTS_FILE = "contacts.json"


def load_contacts() -> dict[str, str]:
    path = jev_file(_CONTACTS_FILE)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k).strip().lower(): str(v).strip() for k, v in data.items() if v}


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def resolve_contact(name_or_phone: str) -> str:
    """Resolve a spoken name or raw number to a wa.me-compatible digit string.

    Raises ToolError with a helpful message when the name is unknown so
    Jev can ask Aarya for the number instead of guessing.
    """
    raw = name_or_phone.strip()
    if _digits(raw) and len(_digits(raw)) >= 7 and not re.search(r"[a-zA-Z]", raw):
        return _digits(raw)
    contacts = load_contacts()
    key = raw.lower()
    if key in contacts:
        number = _digits(contacts[key])
        if number:
            return number
    known = ", ".join(sorted(contacts)) if contacts else "none yet"
    raise ToolError(
        f"I don't have a WhatsApp number for '{raw}'. Known contacts: {known}. "
        "Add the number to ~/.jev/contacts.json, or say the number directly."
    )
