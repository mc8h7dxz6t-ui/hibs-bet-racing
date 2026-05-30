from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

from hibs_racing.hibs_brand import hibs_brand_context
from hibs_racing.models.feature_impact import impact_artifact_paths, load_feature_impact_report
from hibs_racing.monitor import monitor_snapshot
from hibs_racing.odds.market_steam import latest_gauges, latest_triggers, poll_matchbook_odds_once
from hibs_racing.place.paper_ledger import build_tracker_dict, export_ledger_csv, settle_paper_bets
from hibs_racing.portfolio.summary_bar import portfolio_summary_dict
from hibs_racing.portfolio.unified import build_unified_portfolio
from hibs_racing.cards.refresh import refresh_cards
from hibs_racing.config import db_path, load_config
from hibs_racing.web_format import fmt_num, fmt_pct
from hibs_racing.web_service import dashboard_context, health_status

ROOT = Path(__file__).resolve().parents[2]


def create_app() -> Flask:
    load_dotenv(ROOT / ".env")
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
        return ctx

    def _cors_summary(resp):
        if os.environ.get("HIBS_PORTFOLIO_CORS", "").strip() in {"1", "true", "yes"}:
            resp.headers["Access-Control-Allow-Origin"] = os.environ.get("HIBS_PORTFOLIO_CORS_ORIGIN", "*")
        return resp

    @app.route("/")
    def index():
        ctx = dashboard_context()
        return render_template("dashboard.html", **ctx)

    @app.route("/insights")
    def insights_page():
        ctx = dashboard_context()
        ctx.update(insights_context(top_n=10))
        return render_template("insights.html", **ctx)

    @app.route("/api/picks")
    def api_picks():
        from hibs_racing.web_service import insights_context

        top_n = int(request.args.get("top", "10"))
        return jsonify(insights_context(top_n=top_n))

    @app.route("/backtest")
    def backtest_page():
        ctx = dashboard_context()
        return render_template("backtest.html", **ctx)

    @app.route("/tracker")
    def tracker_page():
        ctx = dashboard_context()
        ctx["tracker"] = build_tracker_dict()
        return render_template("tracker.html", **ctx)

    @app.route("/api/tracker")
    def api_tracker():
        return jsonify(build_tracker_dict())

    @app.route("/api/tracker/export.csv")
    def api_tracker_csv():
        body = export_ledger_csv()
        return Response(
            body,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=hibs-racing-ledger.csv"},
        )

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
        ctx["portfolio"] = build_unified_portfolio()
        ctx["market_steam"] = {"triggers": latest_triggers(limit=20)}
        return render_template("portfolio.html", **ctx)

    @app.route("/api/portfolio")
    def api_portfolio():
        return jsonify(build_unified_portfolio())

    @app.route("/api/portfolio/summary")
    def api_portfolio_summary():
        return _cors_summary(jsonify(portfolio_summary_dict()))

    @app.route("/api/market-steam")
    def api_market_steam():
        refresh = request.args.get("poll", "0") == "1"
        if refresh:
            report = poll_matchbook_odds_once(pre_race_only=True)
            return jsonify(report.to_dict())
        return jsonify({"triggers": latest_triggers(limit=50), "gauges": latest_gauges(limit=30)})

    @app.route("/api/feature-impact")
    def api_feature_impact():
        report = load_feature_impact_report()
        return jsonify(report or {"ok": False, "message": "Run train-ranker first"})

    @app.route("/models/feature_impact.svg")
    def feature_impact_svg():
        _, svg_path = impact_artifact_paths()
        if not svg_path.exists():
            return Response("Not found", status=404)
        return Response(svg_path.read_text(encoding="utf-8"), mimetype="image/svg+xml")

    @app.route("/status")
    def status_page():
        return render_template(
            "status.html",
            health=health_status(),
            feature_impact=load_feature_impact_report(),
            market_gauges=latest_gauges(limit=40),
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
        odds_source = request.args.get("odds_source", "auto")
        window = request.args.get("window", "24")
        window_hours = int(window) if window.isdigit() else 24
        try:
            stats = refresh_cards(
                source=source,
                region=region,
                day=day,
                odds_source=odds_source,
                window_hours=window_hours if window_hours > 0 else None,
            )
            monitor = monitor_snapshot(refresh=False, settle=True)
            return jsonify({"ok": True, **stats, "monitor": monitor})
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
