from __future__ import annotations

from pathlib import Path

import pytest

from product_scraper.config import Settings
from product_scraper.proxy import ProxySettings

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(*parts: str) -> str:
    return (FIXTURES.joinpath(*parts)).read_text(encoding="utf-8")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        proxy=ProxySettings(
            scheme="http",
            host="p.webshare.io",
            port=80,
            username="user",
            password="secret",
        ),
        proxy_check_url="https://ipv4.webshare.io/",
        http_backend="httpx",
        http_timeout_seconds=30,
        http_retries=1,
        http_retry_delay_seconds=0,
        http_headless=True,
        db_host="127.0.0.1",
        db_port=3306,
        db_name="boofstore_db",
        db_user="root",
        db_password="secret",
        default_stock=10,
        default_user_id=1,
        default_color_id=1,
        default_brand_slug="decathlon",
    )
