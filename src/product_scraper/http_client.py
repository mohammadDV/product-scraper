from __future__ import annotations

import sys
import time
from typing import Protocol

from product_scraper.config import Settings
from product_scraper.exceptions import CloudflareBlockedError, ConfigurationError, HttpError

BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

_RETRYABLE = (CloudflareBlockedError, HttpError)


class HttpClient(Protocol):
    def get(self, url: str) -> str:
        """Return response body text."""


_CF_HINTS = (
    "just a moment",
    "bir dakika lütfen",
    "_cf_chl_opt",
    "cdn-cgi/challenge-platform",
    "cf-challenge",
)


def looks_like_cloudflare(html: str) -> bool:
    lowered = html.lower()
    return any(hint in lowered for hint in _CF_HINTS)


def _raise_for_response(url: str, status_code: int, html: str) -> None:
    if looks_like_cloudflare(html):
        raise CloudflareBlockedError(url)
    if status_code >= 400:
        raise HttpError(url, status_code)


class HttpxClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get(self, url: str) -> str:
        import httpx

        try:
            with httpx.Client(
                proxy=self._settings.proxy.httpx_proxy(),
                headers=BROWSER_HEADERS,
                follow_redirects=True,
                timeout=self._settings.http_timeout_seconds,
            ) as client:
                response = client.get(url)
        except httpx.HTTPError as exc:
            raise HttpError(url, 0) from exc
        _raise_for_response(url, response.status_code, response.text)
        return response.text


class CurlCffiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get(self, url: str) -> str:
        from curl_cffi import requests

        try:
            proxy_url = self._settings.proxy.url()
            response = requests.get(
                url,
                proxies={"http": proxy_url, "https": proxy_url} if proxy_url else None,
                impersonate="chrome",
                timeout=self._settings.http_timeout_seconds,
                headers=BROWSER_HEADERS,
                allow_redirects=True,
            )
        except Exception as exc:
            raise HttpError(url, 0) from exc
        _raise_for_response(url, response.status_code, response.text)
        return response.text


class RetryingHttpClient:
    def __init__(self, inner: HttpClient, retries: int, delay_seconds: float) -> None:
        self._inner = inner
        self._retries = max(0, retries)
        self._delay_seconds = max(0.0, delay_seconds)

    def get(self, url: str) -> str:
        attempts = self._retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self._inner.get(url)
            except _RETRYABLE as exc:
                last_error = exc
                if attempt >= attempts:
                    raise
                print(
                    f"retry {attempt}/{self._retries} after {type(exc).__name__}",
                    file=sys.stderr,
                )
                if self._delay_seconds:
                    time.sleep(self._delay_seconds)
        raise last_error  # pragma: no cover


def create_http_client(settings: Settings) -> HttpClient:
    if settings.http_backend == "httpx":
        inner: HttpClient = HttpxClient(settings)
    elif settings.http_backend == "curl_cffi":
        inner = CurlCffiClient(settings)
    elif settings.http_backend == "playwright":
        from product_scraper.browser_client import PlaywrightClient

        inner = PlaywrightClient(settings)
    elif settings.http_backend == "camoufox":
        from product_scraper.browser_client import CamoufoxClient

        inner = CamoufoxClient(settings)
    else:
        raise ConfigurationError("HTTP_BACKEND must be camoufox, playwright, curl_cffi, or httpx")
    return RetryingHttpClient(inner, settings.http_retries, settings.http_retry_delay_seconds)
