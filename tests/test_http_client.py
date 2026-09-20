from __future__ import annotations

import pytest

from product_scraper.exceptions import CloudflareBlockedError, HttpError
from product_scraper.http_client import RetryingHttpClient


class FlakyHttpClient:
    def __init__(self, failures: int, html: str, error: type[Exception] = CloudflareBlockedError) -> None:
        self.failures = failures
        self.html = html
        self.error = error
        self.calls = 0

    def get(self, url: str) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            if self.error is HttpError:
                raise HttpError(url, 503)
            raise self.error(url)
        return self.html


def test_retry_succeeds_on_second_attempt() -> None:
    inner = FlakyHttpClient(failures=1, html="<html><h1>ok</h1></html>")
    client = RetryingHttpClient(inner, retries=1, delay_seconds=0)

    html = client.get("https://www.decathlon.com.tr/p/test")

    assert html == "<html><h1>ok</h1></html>"
    assert inner.calls == 2


def test_retry_gives_up_after_one_retry() -> None:
    inner = FlakyHttpClient(failures=3, html="<html><h1>ok</h1></html>")
    client = RetryingHttpClient(inner, retries=1, delay_seconds=0)

    with pytest.raises(CloudflareBlockedError):
        client.get("https://www.decathlon.com.tr/p/test")
    assert inner.calls == 2


def test_retry_also_covers_http_errors() -> None:
    inner = FlakyHttpClient(failures=1, html="<html><h1>ok</h1></html>", error=HttpError)
    client = RetryingHttpClient(inner, retries=1, delay_seconds=0)

    assert client.get("https://example.com") == "<html><h1>ok</h1></html>"
    assert inner.calls == 2
