from __future__ import annotations

import html
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

from hibs_racing.hibs_brand import hibs_brand_context
from hibs_racing.product_links import product_bar_context
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
from hibs_racing.cards.refresh import refresh_cards
from hibs_racing.config import db_path, load_config
from hibs_racing.web_format import fmt_num, fmt_pct
from hibs_racing.web_service import (
    cards_deep_link_context,
    dashboard_context,
    health_status,
    insights_context,
    shell_health_status,
)
from hibs_racing.middleware.auth import require_api_key, validate_auth_config
from hibs_racing.utils.ui_settings import (
    apply_saved_ui_env,
    monetization_form_payload,
    save_ui_monetization,
)

ROOT = Path(__file__).resolve().parents[2]
FAQ_PATH = ROOT / "docs" / "TECHNICAL_DUE_DILIGENCE_FAQ.md"

_HEALTH_CACHE: dict = {"t": 0.0, "payload": None}
_HEALTH_TTL_SEC = float(os.environ.get("HIBS_RACING_HEALTH_TTL_SEC", "20"))
_SHELL_HEALTH_CACHE: dict = {"t": 0.0, "status": None}
_SHELL_HEALTH_TTL_SEC = float(os.environ.get("HIBS_SHELL_HEALTH_TTL_SEC", "30"))


def _safe_portfolio_payload(*, racing_limit: int = 200, history_days: int | None = None) -> dict:
    try:
        return build_racing_portfolio(racing_limit=racing_limit, history_days=history_days)
    except Exception as exc:
        return {
            "ok": False,
            "mode": "analytics",
            "error": str(exc)[:200],
            "summary": {
                "total_rows": 0,
                "racing_rows": 0,
                "racing_pnl_units": 0.0,
                "combined_pnl_units": 0.0,
                "racing_settled": 0,
                "open_bets": 0,
            },
            "ledger": [],
            "links": {"racing_tracker": "/tracker"},
        }


def _channel_digest_preview(ctx: dict | None = None) -> str:
    """Render-only digest copy — reuses dashboard ctx so DQ filters match Smart Portfolio."""
    try:
        from hibs_racing.daily.smart_picks import filter_smart_picks, format_digest_message
        from hibs_racing.web_service import novice_pick_candidates

        if ctx is None:
            ctx = dashboard_context()
        candidates = novice_pick_candidates(ctx.get("meetings") or [])
        picks = filter_smart_picks(candidates, limit=3)
        engine = ctx.get("engine_top_picks") or []
        return format_digest_message(
            {
                "picks": picks,
                "engine_top_picks": engine,
                "card_dates": ctx.get("card_dates") or [],
            },
        )
    except Exception:
        return (
            "🏇 Hibs Racing Intelligence — Daily Value Sheet\n"
            "Cards: today\n\n"
            "Engine refresh pending — cards loading for today's meeting window.\n"
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
    validate_auth_config()
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "hibs-racing-dev")
    app.add_template_filter(fmt_num, "fmt_num")
    app.add_template_filter(fmt_pct, "fmt_pct")
    from hibs_racing.ui_shell import static_v

    app.jinja_env.globals["static_v"] = static_v

    def _cached_shell_health():
        import time as _time

        now = _time.monotonic()
        if (
            _SHELL_HEALTH_CACHE["status"] is not None
            and (now - float(_SHELL_HEALTH_CACHE["t"])) < _SHELL_HEALTH_TTL_SEC
        ):
            return _SHELL_HEALTH_CACHE["status"]
        hs = shell_health_status()
        _SHELL_HEALTH_CACHE["t"] = now
        _SHELL_HEALTH_CACHE["status"] = hs
        return hs

    @app.context_processor
    def inject_brand() -> dict:
        from hibs_racing.ui_shell import ui_shell_context

        ctx = hibs_brand_context()
        ctx.update(ui_shell_context())
        ctx.update(product_bar_context(active="racing"))
        ctx["portfolio_full_url"] = "/portfolio"
        ctx["health"] = _cached_shell_health()
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
        return render_template("insights.html", **insights_context(top_n=10))

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
    @require_api_key
    def api_settle_paper():
        try:
            result = settle_paper_bets()
            return jsonify({"ok": True, **result})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/portfolio")
    def portfolio_page():
        ctx = dashboard_context()
        ctx["portfolio"] = _safe_portfolio_payload()
        return render_template("portfolio.html", **ctx)

    @app.route("/api/portfolio")
    def api_portfolio():
        return jsonify(_safe_portfolio_payload())

    @app.route("/api/portfolio/summary")
    def api_portfolio_summary():
        payload = _safe_portfolio_payload(racing_limit=100)
        s = payload.get("summary") or {}
        racing_stats = payload.get("racing_stats") or {}
        pnl = s.get("racing_pnl_units")
        summary = {
            "ok": payload.get("ok", True),
            "mode": "analytics",
            "updated_at": payload.get("updated_at"),
            "combined_pnl_units": pnl,
            "racing_pnl_units": pnl,
            "racing_settled": s.get("racing_settled"),
            "racing_open": racing_stats.get("open_bets", 0),
            "links": payload.get("links") or {},
        }
        if payload.get("error"):
            summary["error"] = payload["error"]
        return _cors_summary(jsonify(summary))

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
    @require_api_key(methods=("POST",))
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

    @app.route("/api/monetization/venues")
    def api_monetization_venues():
        from hibs_racing.utils.monetization import public_monetization_payload

        return jsonify(public_monetization_payload())

    @app.route("/status")
    def status_page():
        hs = health_status()
        return render_template(
            "status.html",
            health=hs,
            evidence_truth=hs.evidence_truth,
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
    @require_api_key
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
    @require_api_key
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

    @app.route("/api/tips/combinations")
    def api_tips_combinations():
        from hibs_racing.tips.combinations_api import combinations_for_date

        db = db_path(load_config())
        card_date = (request.args.get("date") or "").strip() or None
        return jsonify(combinations_for_date(db, card_date=card_date))

    @app.route("/api/win-engine/predictions")
    def api_win_engine_predictions():
        from hibs_racing.features.store import connect
        from hibs_racing.models.win_engine_circuit import public_release_allowed
        from hibs_racing.models.win_engine_insights import build_runner_insights
        from hibs_racing.models.win_engine_store import load_calibration_state

        if not public_release_allowed(db_path(load_config())):
            return jsonify({"ok": False, "error": "win_engine_inactive"}), 404
        db = db_path(load_config())
        card_date = (request.args.get("date") or "").strip() or None
        if not card_date:
            from datetime import date

            card_date = date.today().isoformat()
        insights = build_runner_insights(db, card_date)
        with connect(db) as conn:
            cal = load_calibration_state(conn)
        return jsonify(
            {
                "ok": True,
                "card_date": card_date,
                "calibration": cal,
                "insights": insights or {},
            }
        )

    @app.route("/api/trading/sandbox")
    def api_trading_sandbox():
        """Read-only racing execution sandbox — no order dispatch."""
        from hibs_racing.trading.status_plane import read_status
        from hibs_racing.trading.liquidity_router import recent_hedged_events, recent_routing_decisions
        from hibs_racing.trading.store import recent_simulated_trades

        limit = min(int(request.args.get("limit", 20)), 50)
        status = read_status()
        return jsonify(
            {
                **status,
                "recent_simulated_trades": recent_simulated_trades(limit=limit),
                "recent_routing_decisions": recent_routing_decisions(limit=limit),
                "recent_hedged_events": recent_hedged_events(limit=limit),
            }
        )

    @app.route("/api/trading/dispatch", methods=["POST"])
    @require_api_key(methods=("POST",))
    def api_trading_dispatch():
        """Workspace order dispatch — routes through execution governor (simulated when live disabled)."""
        from hibs_racing.trading.delta_cache import MarketDeltaCache
        from hibs_racing.trading.execution_governor import ExecutionGovernor, build_order_payload
        from hibs_racing.trading.status_plane import daemon_active

        if not daemon_active():
            return jsonify({"ok": False, "error": "trading_daemon_inactive"}), 503
        body = request.get_json(silent=True) or {}
        selection = str(body.get("selection") or "").strip()
        odds = float(body.get("odds") or 2.0)
        stake = float(body.get("stake") or 2.0)
        market_id = str(body.get("market_id") or body.get("runner_id") or selection or "ws")
        runner_id = str(body.get("runner_id") or selection or "ws")
        governor = ExecutionGovernor(cache=MarketDeltaCache())
        payload = build_order_payload(
            market_id=market_id,
            runner_id=runner_id,
            odds=odds,
            stake=stake,
        )
        payload["selection"] = selection
        payload["source"] = str(body.get("source") or "api_trading_dispatch")
        result = governor.dispatch(payload).to_dict()
        try:
            from hibs_racing.trading.execution_intent_ledger import append_execution_intent

            append_execution_intent(verdict=result, source="api_trading_dispatch", trace_id=str(body.get("trace_id") or ""))
        except Exception:
            pass
        return jsonify({"ok": bool(result.get("allowed")), "verdict": result})

    @app.route("/api/stream/deltas")
    def api_stream_deltas():
        """SSE trading status stream — low-latency UI feed from daemon heartbeat."""
        import json
        import time as _time

        from flask import Response

        from hibs_racing.trading.status_plane import read_status

        def generate():
            last_ts = 0.0
            while True:
                status = read_status(max_age_sec=60.0)
                ts = float(status.get("ts") or 0)
                if ts != last_ts:
                    last_ts = ts
                    yield f"data: {json.dumps({'type': 'trading_status', 'status': status}, default=str)}\n\n"
                yield ": keepalive\n\n"
                _time.sleep(1.0)

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.route("/api/ping")
    def api_ping():
        return jsonify({"ok": True, "product": "hibs-racing"})

    @app.route("/api/live")
    def api_live():
        from hibs_racing.config import db_path, load_config
        from hibs_racing.features.store import connect

        try:
            with connect(db_path(load_config())) as conn:
                conn.execute("SELECT 1").fetchone()
            return jsonify({"ok": True, "tier": "liveness"})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)[:120]}), 503

    @app.route("/api/ready")
    def api_ready():
        from hibs_racing.config import db_path, load_config

        db_ok = False
        db_err = ""
        cfg_db = ""
        runners = 0
        try:
            cfg_db = str(db_path(load_config()))
            import sqlite3

            conn = sqlite3.connect(f"file:{cfg_db}?mode=ro", uri=True, timeout=5.0)
            try:
                conn.execute("SELECT 1").fetchone()
                row = conn.execute("SELECT COUNT(*) FROM upcoming_runners").fetchone()
                runners = int(row[0] or 0) if row else 0
                db_ok = True
            finally:
                conn.close()
        except Exception as exc:
            db_err = str(exc)[:120]

        ok = db_ok and runners > 0
        return jsonify(
            {
                "ok": ok,
                "tier": "readiness",
                "db_ok": db_ok,
                "db_path": cfg_db,
                "runners_loaded": runners,
                "error": db_err or None,
            }
        ), (200 if ok else 503)

    @app.route("/api/scrapers/catalog")
    def api_scrapers_catalog():
        from hibs_racing.cards.runner_field_api import scraper_catalog_payload

        return jsonify(scraper_catalog_payload())

    @app.route("/api/scrape/status")
    def api_scrape_status():
        from hibs_racing.scrapers.racing_scrape_api import scrape_status_payload

        return jsonify(scrape_status_payload())

    @app.route("/api/scrape/cards")
    def api_scrape_cards():
        from hibs_racing.scrapers.racing_scrape_api import list_cards_payload

        enrich = request.args.get("enrich", "0") == "1"
        rescue = request.args.get("rescue", "0") == "1"
        return jsonify(list_cards_payload(slim=not enrich, rescue=rescue))

    @app.route("/api/scrape/resilience")
    def api_scrape_resilience():
        from hibs_racing.scrapers.robust_scrape_cycle import read_robust_scrape_status
        from hibs_racing.scrapers.scrape_resilience import scrape_resilience_status

        return jsonify(
            {
                "ok": True,
                "resilience": scrape_resilience_status(),
                "last_cycle": read_robust_scrape_status(),
            }
        )

    @app.route("/api/runner/<runner_id>")
    def api_runner_fields(runner_id: str):
        from hibs_racing.cards.runner_field_api import resolve_runner_fields

        rescue = request.args.get("rescue", "0") == "1"
        payload = resolve_runner_fields(runner_id, rescue=rescue)
        if not payload:
            return jsonify({"ok": False, "error": "runner_not_found", "runner_id": runner_id}), 404
        return jsonify({"ok": True, **payload})

    @app.route("/api/evidence")
    def api_racing_evidence():
        from hibs_racing.evidence_gates import racing_evidence_gates

        return jsonify(racing_evidence_gates())

    @app.route("/api/health")
    def api_health():
        import time as _time

        force = request.args.get("full", "0") == "1"
        now = _time.monotonic()
        if (
            not force
            and _HEALTH_CACHE["payload"] is not None
            and (now - float(_HEALTH_CACHE["t"])) < _HEALTH_TTL_SEC
        ):
            return jsonify(_HEALTH_CACHE["payload"])
        try:
            payload = health_status().to_dict()
        except Exception as exc:
            return jsonify({"ok": False, "tier": "deep", "error": str(exc)[:120]}), 503
        _HEALTH_CACHE["t"] = now
        _HEALTH_CACHE["payload"] = payload
        return jsonify(payload)

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
    @require_api_key
    def api_refresh():
        from hibs_racing.scrapers.racing_scrape_api import (
            odds_coverage_summary,
            resolve_cards_source,
            run_thin_rescue_pass,
        )

        source = resolve_cards_source(request.args.get("source", "auto"))
        region = request.args.get("region", "gb")
        day = int(request.args.get("day", "1"))
        odds_source = os.environ.get("HIBS_ODDS_SOURCE") or request.args.get("odds_source", "auto")
        window = request.args.get("window", "24")
        window_hours = int(window) if window.isdigit() else 24
        paper_on_refresh = bool(load_config().get("paper", {}).get("log_on_refresh", True))

        def _do_refresh(src: str) -> dict:
            return refresh_cards(
                source=src,
                region=region,
                day=day,
                odds_source=odds_source,
                window_hours=window_hours if window_hours > 0 else None,
                paper=paper_on_refresh,
            )

        stats: dict | None = None
        err: Exception | None = None
        try:
            stats = _do_refresh(source)
        except Exception as exc:
            err = exc
            if source == "racing_api":
                from hibs_racing.racing_api_guard import record_forbidden

                record_forbidden(http_status=403, reason=str(exc)[:80])
                fallback = resolve_cards_source("rpscrape")
                if fallback != source:
                    try:
                        stats = _do_refresh(fallback)
                        stats["cards_source_fallback"] = fallback
                        err = None
                    except Exception as exc2:
                        err = exc2

        if err is not None or stats is None:
            return jsonify({"ok": False, "error": str(err)}), 500

        rescue: dict | None = None
        cov = odds_coverage_summary()
        if not cov.get("ok") and os.getenv("HIBS_RACING_ROBUST_RESCUE", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            try:
                rescue = run_thin_rescue_pass()
                stats["thin_rescue"] = rescue
                cov = rescue.get("coverage") or cov
            except Exception as exc:
                stats["thin_rescue_error"] = str(exc)[:120]

        monitor = monitor_snapshot(refresh=False, settle=True)
        payload = {"ok": True, **stats, "monitor": monitor, "odds_coverage": cov}
        if paper_on_refresh and not stats.get("paper_recon_clean", True):
            return jsonify(payload), 503
        return jsonify(payload)

    from hibs_racing.url_prefix import apply_url_prefix

    apply_url_prefix(app)

    @app.errorhandler(404)
    def _win_engine_404(exc):  # noqa: ARG001
        if request.path.startswith("/api/win-engine"):
            return jsonify({"ok": False, "error": "win_engine_unavailable"}), 404
        return jsonify({"ok": False, "error": "not_found"}), 404

    @app.errorhandler(500)
    def _win_engine_safe_500(exc):  # noqa: ARG001
        if request.path.startswith("/api/win-engine"):
            return jsonify({"ok": False, "error": "win_engine_unavailable"}), 404
        return jsonify({"ok": False, "error": "internal_error"}), 500

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
