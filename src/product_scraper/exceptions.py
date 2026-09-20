from __future__ import annotations


class ScraperError(Exception):
    """Base error for this package."""


class ConfigurationError(ScraperError):
    pass


class CloudflareBlockedError(ScraperError):
    def __init__(self, url: str) -> None:
        super().__init__(f"Cloudflare blocked {url}")
        self.url = url


class ParseError(ScraperError):
    pass


class UnknownSiteError(ScraperError):
    def __init__(self, url: str, slug: str | None = None) -> None:
        detail = f"slug={slug!r}" if slug else f"url={url!r}"
        super().__init__(f"No parser registered for {detail}")
        self.url = url
        self.slug = slug


class HttpError(ScraperError):
    def __init__(self, url: str, status_code: int) -> None:
        message = f"Failed to fetch {url}" if status_code == 0 else f"HTTP {status_code} for {url}"
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class PersistenceError(ScraperError):
    pass
