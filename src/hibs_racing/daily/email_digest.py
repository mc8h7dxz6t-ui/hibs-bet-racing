"""Optional SMTP daily digest — detailed Smart Portfolio picks for personal trial."""

from __future__ import annotations

import html
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from hibs_racing.daily.smart_picks import build_morning_smart_picks_explained


def email_digest_configured() -> bool:
    to_addr = os.environ.get("HIBS_DAILY_EMAIL_TO", "").strip()
    host = os.environ.get("SMTP_HOST", "").strip()
    from_addr = os.environ.get("SMTP_FROM", "").strip() or os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    if not (to_addr and host and from_addr and password):
        return False
    if "your_name@" in to_addr.lower():
        return False
    return True


def _env_flag(name: str) -> bool | None:
    """Parse SMTP_USE_SSL / SMTP_SSL style flags; None if unset."""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return None
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return None


def smtp_use_ssl(port: int) -> bool:
    """Implicit TLS (SMTP_SSL) — required for port 465 and some ISPs (e.g. Sky)."""
    if port == 465:
        return True
    for key in ("SMTP_USE_SSL", "SMTP_SSL"):
        flag = _env_flag(key)
        if flag is not None:
            return flag
    return False


def _steam_gate_note(gate: str) -> str:
    g = (gate or "proceed").lower()
    if g == "scale_up":
        return (
            "Steam gate: scale_up — price has shortened vs the 20-minute reference "
            "(firming market; still eligible for the shortlist)."
        )
    if g == "abort":
        return (
            "Steam gate: abort — price drifted out too far vs reference; "
            "excluded from Smart Portfolio (may still appear in full value ledger)."
        )
    if g == "proceed":
        return "Steam gate: proceed — no adverse drift block on morning exchange reference."
    return f"Steam gate: {gate}"


def _place_terms_text(pick: dict[str, Any]) -> str:
    places = pick.get("places")
    pf = pick.get("place_fraction")
    try:
        pfi = int(float(pf) * 4) if pf is not None else 1
    except (TypeError, ValueError):
        pfi = 1
    try:
        pl = int(places) if places is not None else 3
    except (TypeError, ValueError):
        pl = 3
    return f"1/{pfi} odds a place, top {pl}"


def _format_pick_detail_text(pick: dict[str, Any], index: int) -> str:
    horse = pick.get("horse_name") or "?"
    course = pick.get("course") or "?"
    off = pick.get("off_time") or "?"
    card_date = pick.get("card_date") or ""
    race_name = pick.get("race_name") or pick.get("race_id") or ""
    dq = int(pick.get("data_quality_pct") or 0)
    gate = pick.get("steam_gate") or "proceed"
    place_pct = round(float(pick.get("model_place_prob") or 0) * 100)
    combo_pct = round(float(pick.get("combo_bayes_place") or 0) * 100)
    ev = pick.get("ew_combined_ev")
    ev_s = f"{float(ev):+.2f} units" if ev is not None else "n/a"
    win = pick.get("win_decimal")
    win_s = f"{float(win):.2f}" if win is not None else "n/a"
    rank = pick.get("day_rank") or index
    lines = [
        f"{'=' * 60}",
        f"#{index}  {horse}",
        f"    When:  {card_date}  {off}  ·  {course}",
        f"    Race:  {race_name}",
        f"    Bet:   Each-way @ {win_s} win ({_place_terms_text(pick)})",
        f"    Rank:  Smart Portfolio #{rank} for today",
        "",
        "  Selection gates (unchanged engine rules):",
        f"    · Value flag: {'yes' if pick.get('value_flag') else 'no'}",
        f"    · Data quality: {dq}% (minimum 75% for this shortlist)",
        f"    · {_steam_gate_note(str(gate))}",
        "",
        "  Model snapshot:",
        f"    · Place probability: {place_pct}%",
        f"    · Trainer–jockey combo place prior: {combo_pct}%",
        f"    · Each-way combined EV: {ev_s}",
    ]
    mscore = pick.get("model_score")
    if mscore is not None:
        try:
            lines.append(f"    · Listwise rank score in race: {float(mscore):.3f}")
        except (TypeError, ValueError):
            pass
    if pick.get("race_top1_horse"):
        lines.append(
            f"    · Top-1 win pick in this race (model): {pick.get('race_top1_horse')}"
            + (" — same horse" if pick.get("race_top1_horse") == horse else "")
        )
    lines.append("")
    lines.append("  Why this horse:")
    reasons = pick.get("pick_reasons") or [pick.get("pick_summary") or "Model-led place angle."]
    for bullet in reasons:
        lines.append(f"    • {bullet}")
    link = pick.get("monetized_link")
    if link:
        lines.append("")
        lines.append(f"  Partner odds link: {link}")
    return "\n".join(lines)


def format_email_digest_text(payload: dict[str, Any]) -> str:
    """Plain-text detailed digest for email clients."""
    picks = payload.get("picks") or []
    dates = ", ".join(payload.get("card_dates") or []) or "today"
    generated = payload.get("generated_at") or datetime.now(timezone.utc).isoformat()
    lines = [
        "HIBS RACING — Daily Smart Portfolio (personal digest)",
        f"Generated (UTC): {generated}",
        f"Card date(s): {dates}",
        f"Candidates scanned: {payload.get('candidate_count', 0)}",
        f"Qualified shortlist: {payload.get('pick_count', 0)}",
        "",
        "Filters: value_flag + data_quality ≥ 75% + steam gate proceed|scale_up.",
        "Paper ledger logs all value picks at batch time; this email is your curated top list only.",
        "Performance context: SP / paper calibration — not a live-bet guarantee.",
        "",
    ]
    if not picks:
        lines.append("No runners passed all Smart Portfolio gates today.")
        lines.append("Check the dashboard or widen the card window if you expected action.")
    else:
        for i, pick in enumerate(picks, start=1):
            lines.append(_format_pick_detail_text(pick, i))
            lines.append("")
    lines.append("—")
    lines.append("Reproduce: hibs-racing notify-daily --top 3")
    lines.append("Tracker: /tracker?backtest=0 (live paper rows)")
    return "\n".join(lines)


def _format_pick_detail_html(pick: dict[str, Any], index: int) -> str:
    horse = html.escape(str(pick.get("horse_name") or "?"))
    course = html.escape(str(pick.get("course") or "?"))
    off = html.escape(str(pick.get("off_time") or "?"))
    card_date = html.escape(str(pick.get("card_date") or ""))
    race_name = html.escape(str(pick.get("race_name") or ""))
    dq = int(pick.get("data_quality_pct") or 0)
    gate = html.escape(str(pick.get("steam_gate") or "proceed"))
    place_pct = round(float(pick.get("model_place_prob") or 0) * 100)
    combo_pct = round(float(pick.get("combo_bayes_place") or 0) * 100)
    ev = pick.get("ew_combined_ev")
    ev_s = html.escape(f"{float(ev):+.2f}" if ev is not None else "n/a")
    win = pick.get("win_decimal")
    win_s = html.escape(f"{float(win):.2f}" if win is not None else "n/a")
    reasons = pick.get("pick_reasons") or [pick.get("pick_summary") or "Model-led place angle."]
    bullets = "".join(f"<li>{html.escape(str(r))}</li>" for r in reasons)
    link = pick.get("monetized_link")
    link_html = (
        f'<p><a href="{html.escape(str(link))}">Open partner odds</a></p>' if link else ""
    )
    return f"""
<section style="margin:1.2em 0;padding:1em;border:1px solid #334155;border-radius:8px;background:#0f172a;color:#e2e8f0;font-family:system-ui,sans-serif;">
  <h2 style="margin:0 0 0.5em;color:#7cfc00;">#{index} {horse}</h2>
  <p style="margin:0.25em 0;"><strong>When:</strong> {card_date} {off} · <strong>Course:</strong> {course}</p>
  <p style="margin:0.25em 0;"><strong>Race:</strong> {race_name}</p>
  <p style="margin:0.25em 0;"><strong>Bet:</strong> Each-way @ {win_s} ({html.escape(_place_terms_text(pick))})</p>
  <table style="margin:0.75em 0;font-size:0.9em;border-collapse:collapse;">
    <tr><td style="padding:2px 8px 2px 0;color:#94a3b8;">Value flag</td><td>yes</td></tr>
    <tr><td style="padding:2px 8px 2px 0;color:#94a3b8;">Data quality</td><td>{dq}%</td></tr>
    <tr><td style="padding:2px 8px 2px 0;color:#94a3b8;">Steam gate</td><td>{gate}</td></tr>
    <tr><td style="padding:2px 8px 2px 0;color:#94a3b8;">Place prob</td><td>{place_pct}%</td></tr>
    <tr><td style="padding:2px 8px 2px 0;color:#94a3b8;">Combo place prior</td><td>{combo_pct}%</td></tr>
    <tr><td style="padding:2px 8px 2px 0;color:#94a3b8;">EW combined EV</td><td>{ev_s}</td></tr>
  </table>
  <p style="margin:0.5em 0 0.25em;font-weight:600;">Why this horse</p>
  <ul style="margin:0.25em 0;padding-left:1.2em;">{bullets}</ul>
  {link_html}
</section>
"""


def format_email_digest_html(payload: dict[str, Any]) -> str:
    picks = payload.get("picks") or []
    dates = html.escape(", ".join(payload.get("card_dates") or []) or "today")
    generated = html.escape(str(payload.get("generated_at") or ""))
    body = "".join(_format_pick_detail_html(p, i) for i, p in enumerate(picks, start=1))
    if not picks:
        body = "<p>No runners passed Smart Portfolio gates today.</p>"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Hibs Racing Daily</title></head>
<body style="background:#020617;color:#e2e8f0;font-family:system-ui,sans-serif;padding:1em;">
  <header style="margin-bottom:1em;">
    <h1 style="margin:0;color:#7cfc00;">Hibs Racing — Smart Portfolio</h1>
    <p style="margin:0.35em 0;color:#94a3b8;">Card: {dates} · Generated UTC {generated}</p>
    <p style="margin:0.35em 0;font-size:0.9em;">{payload.get('pick_count', 0)} picks from {payload.get('candidate_count', 0)} candidates · DQ≥75% · value + steam gates</p>
  </header>
  {body}
  <footer style="margin-top:1.5em;font-size:0.85em;color:#64748b;">
    <p>Paper ledger records all value flags at 06:00 batch. This email is your curated shortlist only. SP/paper — not live execution advice.</p>
  </footer>
</body></html>"""


def send_daily_email_digest(payload: dict[str, Any] | None = None, *, limit: int = 3) -> dict[str, Any]:
    """Send detailed digest via SMTP when HIBS_DAILY_EMAIL_TO + SMTP_* are set."""
    if not email_digest_configured():
        return {
            "ok": False,
            "skipped": True,
            "channel": "email",
            "reason": "Set HIBS_DAILY_EMAIL_TO, SMTP_HOST, SMTP_FROM (or SMTP_USER)",
        }

    if payload is None:
        payload = build_morning_smart_picks_explained(limit=limit)

    to_raw = os.environ.get("HIBS_DAILY_EMAIL_TO", "").strip()
    recipients = [a.strip() for a in to_raw.split(",") if a.strip()]
    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "587") or "587")
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    from_addr = os.environ.get("SMTP_FROM", "").strip() or user
    use_ssl = smtp_use_ssl(port)
    use_tls = (
        not use_ssl
        and os.environ.get("SMTP_USE_TLS", "1").strip().lower() not in ("0", "false", "no")
    )
    subject_prefix = os.environ.get("HIBS_DAILY_EMAIL_SUBJECT", "Hibs Racing").strip()

    dates = ", ".join(payload.get("card_dates") or []) or "today"
    subject = f"{subject_prefix} — {payload.get('pick_count', 0)} picks · {dates}"

    text_body = format_email_digest_text(payload)
    html_body = format_email_digest_html(payload)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_cls(host, port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
            if user and password:
                try:
                    smtp.login(user, password)
                except smtplib.SMTPServerDisconnected as exc:
                    return {
                        "ok": False,
                        "channel": "email",
                        "error": (
                            "SMTP login rejected (connection closed). Use a Sky/Yahoo "
                            "app password from Account security → Generate app password "
                            "(16 characters), not your Sky web PIN or mailbox login."
                        ),
                        "detail": str(exc),
                        "to": recipients,
                    }
            smtp.sendmail(from_addr, recipients, msg.as_string())
        return {
            "ok": True,
            "channel": "email",
            "to": recipients,
            "pick_count": payload.get("pick_count"),
            "subject": subject,
        }
    except (OSError, smtplib.SMTPException) as exc:
        return {"ok": False, "channel": "email", "error": str(exc), "to": recipients}
