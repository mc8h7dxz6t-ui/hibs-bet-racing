from __future__ import annotations

import imaplib
import os
from typing import Any

from hibs_racing.tips.email_load import LoadedEmail, load_eml_bytes


class ImapConfigError(Exception):
    pass


def imap_settings() -> dict[str, Any]:
    host = os.environ.get("TIPSTER_IMAP_HOST", "").strip()
    user = os.environ.get("TIPSTER_IMAP_USER", "").strip()
    password = os.environ.get("TIPSTER_IMAP_PASSWORD", "").strip()
    return {
        "host": host,
        "port": int(os.environ.get("TIPSTER_IMAP_PORT", "993")),
        "user": user,
        "password": password,
        "folder": os.environ.get("TIPSTER_IMAP_FOLDER", "INBOX").strip() or "INBOX",
        "from_filter": os.environ.get("TIPSTER_IMAP_FROM", "").strip(),
        "unseen_only": os.environ.get("TIPSTER_IMAP_UNSEEN_ONLY", "1").strip().lower() not in {"0", "false", "no"},
        "mark_read": os.environ.get("TIPSTER_IMAP_MARK_READ", "0").strip().lower() in {"1", "true", "yes"},
        "limit": int(os.environ.get("TIPSTER_IMAP_LIMIT", "30")),
    }


def imap_configured() -> bool:
    cfg = imap_settings()
    return bool(cfg["host"] and cfg["user"] and cfg["password"])


def fetch_imap_messages(
    *,
    unseen_only: bool | None = None,
    limit: int | None = None,
    from_filter: str | None = None,
) -> list[LoadedEmail]:
    """
    Pull tip emails directly from IMAP (Gmail, iCloud, Outlook, etc.).
    Requires TIPSTER_IMAP_* in .env — no need to save .eml files.
    """
    cfg = imap_settings()
    if not imap_configured():
        raise ImapConfigError(
            "IMAP not configured. Set TIPSTER_IMAP_HOST, TIPSTER_IMAP_USER, TIPSTER_IMAP_PASSWORD in .env"
        )

    unseen_only = cfg["unseen_only"] if unseen_only is None else unseen_only
    limit = cfg["limit"] if limit is None else limit
    from_filter = from_filter if from_filter is not None else cfg["from_filter"]

    criteria = ["UNSEEN"] if unseen_only else ["ALL"]
    if from_filter:
        criteria.append(f'FROM "{from_filter}"')
    search = f"({' '.join(criteria)})"

    mail = imaplib.IMAP4_SSL(cfg["host"], cfg["port"])
    try:
        mail.login(cfg["user"], cfg["password"])
        status, _ = mail.select(cfg["folder"], readonly=not cfg["mark_read"])
        if status != "OK":
            raise ImapConfigError(f"Could not open folder: {cfg['folder']}")

        status, data = mail.search(None, search)
        if status != "OK" or not data or not data[0]:
            return []

        ids = data[0].split()
        ids = ids[-limit:]
        loaded: list[LoadedEmail] = []

        for num in ids:
            status, fetched = mail.fetch(num, "(RFC822)")
            if status != "OK" or not fetched or not fetched[0]:
                continue
            raw = fetched[0][1]
            if not isinstance(raw, bytes):
                continue
            label = f"imap:{cfg['folder']}:{num.decode() if isinstance(num, bytes) else num}"
            loaded.append(load_eml_bytes(raw, source_label=label))

            if cfg["mark_read"]:
                mail.store(num, "+FLAGS", "\\Seen")

        return loaded
    finally:
        try:
            mail.logout()
        except Exception:
            pass
