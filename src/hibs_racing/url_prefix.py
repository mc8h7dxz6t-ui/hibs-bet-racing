"""Production /racing subpath support (nginx X-Script-Name)."""

from __future__ import annotations

import os
import re

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from hibs_racing.product_links import product_bar_context

_ALREADY_PREFIXED = re.compile(r"^/(?:racing|api/racing)(?:/|$)")
_LOCALHOST_FOOTBALL = re.compile(r"https?://127\.0\.0\.1:5000/?")


def url_prefix() -> str:
    return (os.getenv("HIBS_URL_PREFIX") or "").strip().rstrip("/")


def _site_domain() -> str:
    return (os.getenv("HIBS_DOMAIN") or "hibs-bet.co.uk").strip()


def prefix_path(path: str, prefix: str) -> str:
    if not path.startswith("/") or path.startswith("//"):
        return path
    if _ALREADY_PREFIXED.match(path):
        return path
    if path.startswith("/api/"):
        return "/api/racing" + path[4:]
    return prefix + path


def racing_api_path(subpath: str) -> str:
    """Browser-facing racing API path (respects /racing production prefix)."""
    sub = (subpath or "").lstrip("/")
    path = f"/api/{sub}"
    pref = url_prefix()
    if pref:
        return prefix_path(path, pref)
    return path


def racing_page_path(subpath: str = "") -> str:
    """Browser-facing racing HTML path."""
    sub = (subpath or "").lstrip("/")
    pref = url_prefix()
    if not sub:
        return pref or "/"
    path = f"/{sub}"
    if pref:
        return prefix_path(path, pref)
    return path


def rewrite_html_paths(html: str, prefix: str) -> str:
    """Rewrite root-relative href/src/fetch/url() paths for subpath deploy."""
    if not prefix:
        return html

    football_home = (
        os.getenv("HIBS_FOOTBALL_HOME_URL") or f"https://{_site_domain()}/"
    ).rstrip("/") + "/"
    html = _LOCALHOST_FOOTBALL.sub(football_home, html)

    def attr_repl(match: re.Match[str]) -> str:
        return match.group(1) + prefix_path(match.group(2), prefix) + match.group(3)

    for pattern in (
        r'(href=")(/[^"]*)(")',
        r"(href=')(/[^']*)(')",
        r'(src=")(/[^"]*)(")',
        r"(src=')(/[^']*)(')",
        r'(action=")(/[^"]*)(")',
        r"(action=')(/[^']*)(')",
        r'(data-fetch-url=")(/[^"]*)(")',
        r"(data-fetch-url=')(/[^']*)(')",
        r'(data-tips-url=")(/[^"]*)(")',
        r"(data-tips-url=')(/[^']*)(')",
        r"(fetch\(')(/[^']*)(')",
        r'(fetch\(")(/[^"]*)(")',
        r"(url\(')(/[^']*)(')",
        r'(url\(")(/[^"]*)(")',
    ):
        html = re.sub(pattern, attr_repl, html)

    portfolio_api = os.getenv("HIBS_PORTFOLIO_API_URL", "/api/racing/portfolio/summary")
    html = html.replace('data-api-url="/api/portfolio/summary"', f'data-api-url="{portfolio_api}"')
    return html


def apply_url_prefix(app: Flask) -> None:
    """Honor nginx X-Script-Name; fix links/API paths on HTML responses."""
    if getattr(app, "_hibs_url_prefix_applied", False):
        return
    app._hibs_url_prefix_applied = True  # type: ignore[attr-defined]

    prefix = url_prefix()
    if prefix:
        app.config["APPLICATION_ROOT"] = prefix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    @app.context_processor
    def _hibs_subpath_product_links():  # noqa: ANN202
        return {
            **product_bar_context(active="racing"),
            "racing_api_path": racing_api_path,
            "racing_page_path": racing_page_path,
        }

    if not prefix:
        return

    @app.after_request
    def _rewrite_subpath_html(response):  # noqa: ANN001
        ctype = (response.content_type or "").lower()
        if "html" not in ctype or response.status_code >= 400:
            return response
        if response.direct_passthrough:
            return response
        try:
            body = response.get_data(as_text=True)
            response.set_data(rewrite_html_paths(body, prefix))
        except Exception:
            pass
        return response
