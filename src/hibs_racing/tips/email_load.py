from __future__ import annotations

import email
import re
from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path


@dataclass
class LoadedEmail:
    path: str
    message_id: str
    subject: str
    received_at: str | None
    card_date: str | None
    body_text: str
    source_kind: str  # eml | txt | paste


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_BREAK_RE = re.compile(r"<\s*br\s*/?\s*>", re.I)


def _html_to_text(html: str) -> str:
    text = _HTML_BREAK_RE.sub("\n", html)
    text = _HTML_TAG_RE.sub(" ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_body(msg: email.message.Message) -> str:
    plain: list[str] = []
    html: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            ctype = part.get_content_type()
            try:
                payload = part.get_content()
            except Exception:
                continue
            if not payload:
                continue
            if ctype == "text/plain":
                plain.append(str(payload))
            elif ctype == "text/html":
                html.append(str(payload))
    else:
        try:
            payload = msg.get_content()
        except Exception:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8", errors="replace")
        if msg.get_content_type() == "text/html":
            html.append(str(payload or ""))
        else:
            plain.append(str(payload or ""))

    if plain:
        return "\n".join(plain).strip()
    if html:
        return _html_to_text("\n".join(html))
    return ""


def _header_datetime(msg: email.message.Message) -> tuple[str | None, str | None]:
    raw = msg.get("Date")
    if not raw:
        return None, None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo:
            dt = dt.astimezone(datetime.now().astimezone().tzinfo)
        iso = dt.replace(microsecond=0).isoformat()
        return iso, dt.strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError):
        return str(raw), None


def load_eml(path: Path) -> LoadedEmail:
    with path.open("rb") as fh:
        msg = email.message_from_binary_file(fh, policy=policy.default)
    received_at, card_date = _header_datetime(msg)
    mid = (msg.get("Message-ID") or f"file:{path.name}").strip()
    subject = (msg.get("Subject") or "").strip()
    body = _extract_body(msg)
    return LoadedEmail(
        path=str(path),
        message_id=mid,
        subject=subject,
        received_at=received_at,
        card_date=card_date,
        body_text=body,
        source_kind="eml",
    )


def load_text_file(path: Path, *, default_date: str | None = None) -> LoadedEmail:
    body = path.read_text(encoding="utf-8", errors="replace")
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    card_date = default_date or mtime.strftime("%Y-%m-%d")
    return LoadedEmail(
        path=str(path),
        message_id=f"paste:{path.name}:{hash(body) & 0xFFFFFFFF:08x}",
        subject=path.stem,
        received_at=mtime.replace(microsecond=0).isoformat(),
        card_date=card_date,
        body_text=body,
        source_kind="txt",
    )


def load_raw_input(path: Path, *, default_date: str | None = None) -> LoadedEmail:
    suffix = path.suffix.lower()
    if suffix == ".eml":
        return load_eml(path)
    return load_text_file(path, default_date=default_date)


def split_paste_chunks(text: str) -> list[str]:
    """Split one paste into multiple emails (forward chains, batch paste)."""
    cleaned = text.replace("\r\n", "\n").strip()
    if not cleaned:
        return []
    if re.search(r"^From:\s", cleaned, re.I | re.MULTILINE):
        parts = re.split(r"(?=^From:\s)", cleaned, flags=re.I | re.MULTILINE)
        return [p.strip() for p in parts if p.strip()]
    parts = re.split(r"\n-{3,}\n", cleaned)
    if len(parts) > 1:
        return [p.strip() for p in parts if p.strip()]
    return [cleaned]


def load_from_message(msg: email.message.Message, *, source_label: str, source_kind: str) -> LoadedEmail:
    received_at, card_date = _header_datetime(msg)
    mid = (msg.get("Message-ID") or f"{source_kind}:{hash(_extract_body(msg)) & 0xFFFFFFFF:08x}").strip()
    subject = (msg.get("Subject") or "").strip()
    return LoadedEmail(
        path=source_label,
        message_id=mid,
        subject=subject,
        received_at=received_at,
        card_date=card_date,
        body_text=_extract_body(msg),
        source_kind=source_kind,
    )


def load_pasted_chunk(
    chunk: str,
    *,
    default_date: str | None = None,
    chunk_index: int = 0,
) -> LoadedEmail:
    """
    Parse copy-pasted content: full email headers, .eml snippet, or body-only.
    """
    chunk = chunk.strip()
    label = f"paste:{chunk_index}"
    looks_like_email = bool(
        re.match(r"^From:\s", chunk, re.I)
        or re.search(r"^Subject:\s", chunk, re.I | re.MULTILINE)
        or re.search(r"^Date:\s", chunk, re.I | re.MULTILINE)
    )
    if looks_like_email:
        try:
            msg = email.message_from_string(chunk, policy=policy.default)
            loaded = load_from_message(msg, source_label=label, source_kind="paste")
            if not loaded.card_date and default_date:
                loaded.card_date = default_date
            return loaded
        except Exception:
            pass

    now = datetime.now().replace(microsecond=0)
    return LoadedEmail(
        path=label,
        message_id=f"paste:{chunk_index}:{hash(chunk) & 0xFFFFFFFF:08x}",
        subject="Pasted tips",
        received_at=now.isoformat(),
        card_date=default_date or now.strftime("%Y-%m-%d"),
        body_text=chunk,
        source_kind="paste",
    )


def load_pasted_text(text: str, *, default_date: str | None = None) -> list[LoadedEmail]:
    return [
        load_pasted_chunk(chunk, default_date=default_date, chunk_index=i)
        for i, chunk in enumerate(split_paste_chunks(text))
    ]


def load_eml_bytes(raw: bytes, *, source_label: str) -> LoadedEmail:
    msg = email.message_from_bytes(raw, policy=policy.default)
    return load_from_message(msg, source_label=source_label, source_kind="imap")

