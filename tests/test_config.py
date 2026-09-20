from __future__ import annotations

import pytest

from product_scraper.config import Settings
from product_scraper.exceptions import ConfigurationError
from product_scraper.proxy import ProxySettings, parse_proxy_url


def test_proxy_url_encodes_credentials() -> None:
    proxy = ProxySettings("http", "p.webshare.io", 80, "tgucpael-rotate", "sn00gql240sx")
    assert proxy.url() == "http://tgucpael-rotate:sn00gql240sx@p.webshare.io:80"


def test_proxy_repr_hides_password() -> None:
    proxy = ProxySettings("http", "p.webshare.io", 80, "user", "super-secret")
    rendered = repr(proxy)
    assert "super-secret" not in rendered
    assert "password=***" in rendered


def test_playwright_proxy_keeps_auth_out_of_server() -> None:
    proxy = ProxySettings("http", "p.webshare.io", 80, "user", "secret")
    assert proxy.playwright_proxy() == {
        "server": "http://p.webshare.io:80",
        "username": "user",
        "password": "secret",
    }


def test_parse_proxy_url() -> None:
    proxy = parse_proxy_url("http://user:pass@p.webshare.io:80")
    assert proxy.host == "p.webshare.io"
    assert proxy.port == 80
    assert proxy.username == "user"
    assert proxy.password == "pass"


def test_settings_from_split_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROXY_URL", raising=False)
    monkeypatch.setenv("PROXY_HOST", "p.webshare.io")
    monkeypatch.setenv("PROXY_PORT", "80")
    monkeypatch.setenv("PROXY_USERNAME", "user")
    monkeypatch.setenv("PROXY_PASSWORD", "secret")
    monkeypatch.setenv("DB_DATABASE", "boofstore_db")
    monkeypatch.setenv("DB_USERNAME", "root")
    monkeypatch.setenv("HTTP_BACKEND", "httpx")
    settings = Settings.from_env(dotenv=False)
    assert settings.proxy.host == "p.webshare.io"
    assert settings.proxy.password == "secret"
    assert "secret" not in repr(settings.proxy)


def test_settings_require_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROXY_HOST", raising=False)
    monkeypatch.delenv("PROXY_URL", raising=False)
    monkeypatch.setenv("DB_DATABASE", "boofstore_db")
    monkeypatch.setenv("DB_USERNAME", "root")
    with pytest.raises(ConfigurationError):
        Settings.from_env(dotenv=False)
