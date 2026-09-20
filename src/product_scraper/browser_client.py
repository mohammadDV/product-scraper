from __future__ import annotations

import os
import time

from product_scraper.config import Settings
from product_scraper.exceptions import CloudflareBlockedError, HttpError
from product_scraper.http_client import looks_like_cloudflare


def _still_challenged(page) -> bool:
    html = page.content()
    title = (page.title() or "").lower()
    return looks_like_cloudflare(html) or looks_like_cloudflare(title)


def wait_for_product_html(page, url: str, timeout_ms: int) -> str:
    deadline = time.monotonic() + timeout_ms / 1000
    while _still_challenged(page):
        if time.monotonic() >= deadline:
            raise CloudflareBlockedError(url)
        page.wait_for_timeout(500)

    remaining_ms = max(1_000, int((deadline - time.monotonic()) * 1000))
    try:
        page.wait_for_selector(
            "span.vtmn-price, .current-selected-model, img.swiper-media__image",
            timeout=remaining_ms,
        )
    except Exception as exc:
        if _still_challenged(page):
            raise CloudflareBlockedError(url) from exc
    page.wait_for_timeout(1_500)

    html = page.content()
    if looks_like_cloudflare(html):
        raise CloudflareBlockedError(url)
    return html


class CamoufoxClient:
    """Anti-detect Firefox that can complete Cloudflare challenges."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get(self, url: str) -> str:
        from camoufox.sync_api import Camoufox

        timeout_ms = int(self._settings.http_timeout_seconds * 1000)
        try:
            with Camoufox(
                headless=self._settings.http_headless,
                proxy=self._settings.proxy.playwright_proxy(),
                geoip=True,
                humanize=True,
                os="windows",
            ) as browser:
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                return wait_for_product_html(page, url, timeout_ms)
        except CloudflareBlockedError:
            raise
        except Exception as exc:
            raise HttpError(url, 0) from exc


class PlaywrightClient:
    """Stock Chromium fallback. Prefer CamoufoxClient against Cloudflare."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get(self, url: str) -> str:
        from playwright.sync_api import sync_playwright

        os.environ.setdefault("PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL", "0")
        timeout_ms = int(self._settings.http_timeout_seconds * 1000)
        try:
            with sync_playwright() as playwright:
                browser = _launch_chromium(
                    playwright,
                    self._settings.proxy.playwright_proxy(),
                    self._settings.http_headless,
                )
                try:
                    context = browser.new_context(
                        viewport={"width": 1366, "height": 768},
                        extra_http_headers={
                            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
                        },
                    )
                    page = context.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    return wait_for_product_html(page, url, timeout_ms)
                finally:
                    browser.close()
        except CloudflareBlockedError:
            raise
        except Exception as exc:
            raise HttpError(url, 0) from exc


def _launch_chromium(playwright, proxy: dict[str, str] | None, headless: bool):
    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
    ]
    last_error: Exception | None = None
    for channel in ("chrome", "chromium", None):
        options = {"headless": headless, "args": args, "proxy": proxy}
        if channel:
            options["channel"] = channel
        try:
            return playwright.chromium.launch(**options)
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError("Could not launch Chromium")
