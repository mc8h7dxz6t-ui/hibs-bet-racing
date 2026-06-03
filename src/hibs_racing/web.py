from __future__ import annotations

import html
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

from hibs_racing.hibs_brand import hibs_brand_context
from hibs_racing.models.feature_impact import impact_artifact_paths, load_feature_impact_report
from hibs_racing.models.ranker_attribution import live_ranker_attribution
from hibs_racing.monitor import monitor_snapshot
from hibs_racing.odds.market_steam import latest_gauges, latest_triggers
from hibs_racing.place.paper_ledger import export_ledger_csv, settle_paper_bets
from hibs_racing.place.public_tracker import (
    automation_ops_status,
    build_public_tracker_dict,
    default_history_days,
    public_tracker_enabled,
)
from hibs_racing.portfolio.racing import build_racing_portfolio
from hibs_racing.portfolio.summary_bar import portfolio_summary_dict
from hibs_racing.cards.refresh import refresh_cards
from hibs_racing.config import db_path, load_config
from hibs_racing.web_format import fmt_num, fmt_pct
from hibs_racing.web_service import cards_deep_link_context, dashboard_context, health_status, insights_context
from hibs_racing.utils.ui_settings import (
    apply_saved_ui_env,
    monetization_form_payload,
    save_ui_monetization,
)

ROOT = Path(__file__).resolve().parents[2]
FAQ_PATH = ROOT / "docs" / "TECHNICAL_DUE_DILIGENCE_FAQ.md"


def _channel_digest_preview(ctx: dict | None = None) -> str:
    """Render-only digest copy — reuses dashboard ctx so DQ filters match Smart Portfolio."""
    try:
        from hibs_racing.daily.smart_picks import filter_smart_picks, format_digest_message
        from hibs_racing.web_service import novice_pick_candidates

        if ctx is None:
            ctx = dashboard_context()
        candidates = novice_pick_candidates(ctx.get("meetings") or [])
        picks = filter_smart_picks(candidates, limit=3)
        return format_digest_message(
            {"picks": picks, "card_dates": ctx.get("card_dates") or []},
        )
    except Exception:
        return (
            "🏇 Hibs Racing Intelligence — Daily Value Sheet\n"
            "Cards: today\n\n"
            "No value picks passed filters today (value + DQ≥75% + steam gate).\n"
            "Tracker: /tracker"
        )


def _render_markdown_simple(text: str) -> str:
    out: list[str] = []
    in_code = False
    in_ul = False
    for line in text.splitlines():
        if line.startswith("```"):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                out.append('<pre class="faq-code"><code>')
                in_code = True
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        if line.startswith("### "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.strip().startswith("- "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            item = html.escape(line.strip()[2:])
            item = re.sub(r"`([^`]+)`", r"<code>\1</code>", item)
            item = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", item)
            out.append(f"<li>{item}</li>")
        elif not line.strip():
            if in_ul:
                out.append("</ul>")
                in_ul = False
        else:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            esc = html.escape(line)
            esc = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)
            esc = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", esc)
            out.append(f"<p>{esc}</p>")
    if in_ul:
        out.append("</ul>")
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def create_app() -> Flask:
    load_dotenv(ROOT / ".env")
    apply_saved_ui_env()
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "hibs-racing-dev")
    app.add_template_filter(fmt_num, "fmt_num")
    app.add_template_filter(fmt_pct, "fmt_pct")

    @app.context_processor
    def inject_brand() -> dict:
        ctx = hibs_brand_context()
        ctx["portfolio_api_url"] = "/api/portfolio/summary"
        ctx["portfolio_full_url"] = "/portfolio"
        ctx["health"] = health_status()
        football_base = os.environ.get("HIBS_FOOTBALL_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
        ctx["hibs_football_base_url"] = football_base
        ctx["hibs_racing_base_url"] = os.environ.get("HIBS_RACING_PUBLIC_URL", "").rstrip("/") or ""
        ctx["hibs_football_home_url"] = football_base + "/"
        ctx["hibs_racing_home_url"] = "/cards"
        ctx["hibs_product_active"] = "racing"
        return ctx

    def _cors_summary(resp):
        if os.environ.get("HIBS_PORTFOLIO_CORS", "").strip() in {"1", "true", "yes"}:
            resp.headers["Access-Control-Allow-Origin"] = os.environ.get("HIBS_PORTFOLIO_CORS_ORIGIN", "*")
        return resp

    def _render_cards():
        ctx = dashboard_context()
        ctx["channel_digest"] = _channel_digest_preview(ctx)
        ctx.update(
            cards_deep_link_context(
                ctx["meetings"],
                race_id=request.args.get("race_id"),
                meeting=request.args.get("meeting"),
                race=request.args.get("race"),
                runner_id=request.args.get("runner_id") or request.args.get("runner"),
            )
        )
        return render_template("dashboard.html", **ctx)

    @app.route("/")
    @app.route("/cards")
    def index():
        return _render_cards()

    @app.route("/insights")
    def insights_page():
        ctx = dashboard_context()
        ctx.update(insights_context(top_n=10))
        return render_template("insights.html", **ctx)

    @app.route("/api/picks")
    def api_picks():
        top_n = int(request.args.get("top", "10"))
        return jsonify(insights_context(top_n=top_n))

    @app.route("/backtest")
    def backtest_page():
        ctx = dashboard_context()
        return render_template("backtest.html", **ctx)

    def _tracker_days() -> int:
        try:
            return max(7, min(90, int(request.args.get("days", default_history_days()))))
        except ValueError:
            return default_history_days()

    def _tracker_backtest() -> bool | None:
        raw = request.args.get("backtest", "").strip().lower()
        if raw in {"1", "true", "yes"}:
            return True
        return False

    @app.route("/tracker")
    @app.route("/track-record")
    def tracker_page():
        if not public_tracker_enabled():
            from flask import abort
            abort(404)
        ctx = dashboard_context()
        ctx["tracker"] = build_public_tracker_dict(
            history_days=_tracker_days(),
            backtest=_tracker_backtest(),
        )
        ctx["tracker_backtest"] = _tracker_backtest()
        ctx["public_read_only"] = True
        from flask import make_response
        resp = make_response(render_template("tracker.html", **ctx))
        resp.headers["Cache-Control"] = "public, max-age=120"
        return resp

    @app.route("/api/tracker")
    def api_tracker():
        from flask import abort

        if not public_tracker_enabled():
            abort(404)
        payload = build_public_tracker_dict(
            history_days=_tracker_days(),
            backtest=_tracker_backtest(),
        )
        resp = jsonify(payload)
        resp.headers["Cache-Control"] = "public, max-age=120"
        resp.headers["Access-Control-Allow-Origin"] = os.environ.get("HIBS_TRACKER_CORS_ORIGIN", "*")
        return resp

    @app.route("/api/tracker/export.csv")
    def api_tracker_csv():
        from flask import abort

        if not public_tracker_enabled():
            abort(404)
        days = _tracker_days()
        backtest = _tracker_backtest()
        body = export_ledger_csv(days=days, backtest=backtest)
        fname = "hibs-racing-oos-track-record.csv" if backtest else "hibs-racing-tracker.csv"
        resp = Response(
            body,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={fname}"},
        )
        resp.headers["Cache-Control"] = "public, max-age=300"
        resp.headers["Access-Control-Allow-Origin"] = os.environ.get("HIBS_TRACKER_CORS_ORIGIN", "*")
        return resp

    @app.route("/api/settle-paper", methods=["POST"])
    def api_settle_paper():
        try:
            result = settle_paper_bets()
            return jsonify({"ok": True, **result})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/portfolio")
    def portfolio_page():
        ctx = dashboard_context()
        ctx["portfolio"] = build_racing_portfolio()
        return render_template("portfolio.html", **ctx)

    @app.route("/api/portfolio")
    def api_portfolio():
        return jsonify(build_racing_portfolio())

    @app.route("/api/portfolio/summary")
    def api_portfolio_summary():
        return _cors_summary(jsonify(portfolio_summary_dict()))

    @app.route("/api/market-steam")
    def api_market_steam():
        if request.args.get("poll", "0") == "1":
            return jsonify(
                {
                    "ok": False,
                    "mode": "batch",
                    "error": "Live polling disabled — morning odds captured at 06:00 daily_refresh only.",
                }
            ), 403
        return jsonify(
            {
                "mode": "batch_snapshot",
                "triggers": latest_triggers(limit=50),
                "gauges": latest_gauges(limit=30),
            }
        )

    @app.route("/api/feature-impact")
    def api_feature_impact():
        report = load_feature_impact_report()
        return jsonify(report or {"ok": False, "message": "Run train-ranker first"})

    @app.route("/api/ranker/attribution")
    def api_ranker_attribution():
        return jsonify(live_ranker_attribution())

    @app.route("/models/feature_impact.svg")
    def feature_impact_svg():
        _, svg_path = impact_artifact_paths()
        if not svg_path.exists():
            return Response("Not found", status=404)
        return Response(svg_path.read_text(encoding="utf-8"), mimetype="image/svg+xml")

    @app.route("/docs/technical-faq")
    def technical_faq_page():
        if not FAQ_PATH.exists():
            from flask import abort

            abort(404)
        md = FAQ_PATH.read_text(encoding="utf-8")
        return render_template(
            "docs_faq.html",
            faq_html=_render_markdown_simple(md),
            faq_title="Architecture Technical FAQ",
        )

    @app.route("/api/daily-digest-preview")
    def api_daily_digest_preview():
        return jsonify({"ok": True, "message": _channel_digest_preview()})

    @app.route("/admin/branding")
    def admin_branding_page():
        return render_template("admin_branding.html")

    @app.route("/settings/monetization")
    def settings_monetization_page():
        payload = monetization_form_payload()
        return render_template(
            "settings_monetization.html",
            monetization_fields=payload["fields"],
            monetization_bootstrap=payload,
        )

    @app.route("/api/settings/monetization", methods=["GET", "POST"])
    def api_settings_monetization():
        if request.method == "GET":
            return jsonify(monetization_form_payload())
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return jsonify({"ok": False, "error": "Expected JSON object"}), 400
        try:
            saved = save_ui_monetization(body)
            return jsonify({"ok": True, "saved_keys": sorted(saved.keys())})
        except OSError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/status")
    def status_page():
        return render_template(
            "status.html",
            health=health_status(),
            feature_impact=load_feature_impact_report(),
            ranker_attribution=live_ranker_attribution(),
            market_gauges=latest_gauges(limit=40),
            automation_ops=automation_ops_status(),
        )

    @app.route("/tips")
    def tips_page():
        from hibs_racing.tips.imap_fetch import imap_configured
        from hibs_racing.tips.store import load_tips, tipster_summary

        db = db_path(load_config())
        return render_template(
            "tips.html",
            tips=load_tips(db, limit=80),
            summary=tipster_summary(db),
            imap_ready=imap_configured(),
        )

    @app.route("/api/tips/paste", methods=["POST"])
    def api_tips_paste():
        from hibs_racing.tips.ingest import ingest_pasted_text

        payload = request.get_json(silent=True) or {}
        text = (payload.get("text") or request.form.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "error": "Empty paste"}), 400
        card_date = payload.get("card_date") or request.form.get("card_date")
        settle = str(payload.get("settle") or request.form.get("settle") or "").lower() in {"1", "true", "yes"}
        try:
            result = ingest_pasted_text(text, default_date=card_date or None, settle=settle)
            return jsonify({"ok": True, **result})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/tips/fetch-imap", methods=["POST"])
    def api_tips_fetch_imap():
        from hibs_racing.tips.imap_fetch import imap_configured
        from hibs_racing.tips.ingest import ingest_from_imap

        if not imap_configured():
            return jsonify({"ok": False, "error": "IMAP not configured in .env"}), 400
        settle = request.args.get("settle", "0") == "1"
        try:
            result = ingest_from_imap(settle=settle)
            return jsonify({"ok": True, **result})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/tips")
    def api_tips_list():
        from hibs_racing.tips.store import load_tips, tipster_summary

        db = db_path(load_config())
        return jsonify({"tips": load_tips(db, limit=100), "summary": tipster_summary(db)})

    @app.route("/api/ping")
    def api_ping():
        return jsonify({"ok": True, "product": "hibs-racing"})

    @app.route("/api/health")
    def api_health():
        return jsonify(health_status().to_dict())

    @app.route("/api/dashboard")
    def api_dashboard():
        return jsonify(
            {
                "health": health_status().to_dict(),
                "card_date": dashboard_context().get("card_date"),
                "runner_count": dashboard_context().get("runner_count"),
                "race_count": dashboard_context().get("race_count"),
            }
        )

    @app.route("/api/monitor")
    def api_monitor():
        refresh = request.args.get("refresh", "0") == "1"
        payload = monitor_snapshot(refresh=refresh, settle=True)
        return jsonify(payload)

    @app.route("/api/refresh", methods=["POST", "GET"])
    def api_refresh():
        source = request.args.get("source", "racing_api")
        region = request.args.get("region", "gb")
        day = int(request.args.get("day", "1"))
        odds_source = os.environ.get("HIBS_ODDS_SOURCE") or request.args.get("odds_source", "auto")
        window = request.args.get("window", "24")
        window_hours = int(window) if window.isdigit() else 24
        try:
            paper_on_refresh = bool(load_config().get("paper", {}).get("log_on_refresh", True))
            stats = refresh_cards(
                source=source,
                region=region,
                day=day,
                odds_source=odds_source,
                window_hours=window_hours if window_hours > 0 else None,
                paper=paper_on_refresh,
            )
            monitor = monitor_snapshot(refresh=False, settle=True)
            payload = {"ok": True, **stats, "monitor": monitor}
            if paper_on_refresh and not stats.get("paper_recon_clean", True):
                return jsonify(payload), 503
            return jsonify(payload)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    return app


def main() -> None:
    app = create_app()
    port = int(os.environ.get("PORT", "5003"))
    host = os.environ.get("HOST", "127.0.0.1")
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"hibs-racing UI → http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
