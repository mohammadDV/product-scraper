from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from product_scraper.exceptions import ConfigurationError
from product_scraper.proxy import ProxySettings, parse_proxy_url


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    proxy: ProxySettings
    proxy_check_url: str
    http_backend: str
    http_timeout_seconds: float
    http_retries: int
    http_retry_delay_seconds: float
    http_headless: bool
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    default_stock: int
    default_user_id: int
    default_color_id: int
    default_brand_slug: str

    @classmethod
    def from_env(cls, env_file: Path | None = None, *, dotenv: bool = True) -> Settings:
        if dotenv:
            load_dotenv(env_file, override=False)

        proxy_url = _env("PROXY_URL")
        if proxy_url:
            proxy = parse_proxy_url(proxy_url)
        else:
            host = _env("PROXY_HOST")
            if not host:
                raise ConfigurationError("Set PROXY_HOST or PROXY_URL")
            proxy = ProxySettings(
                scheme=_env("PROXY_SCHEME", "http") or "http",
                host=host,
                port=_env_int("PROXY_PORT", 80),
                username=_env("PROXY_USERNAME"),
                password=_env("PROXY_PASSWORD"),
            )

        backend = (_env("HTTP_BACKEND", "camoufox") or "camoufox").lower()
        if backend not in {"camoufox", "playwright", "curl_cffi", "httpx"}:
            raise ConfigurationError("HTTP_BACKEND must be camoufox, playwright, curl_cffi, or httpx")

        timeout_default = "60" if backend in {"camoufox", "playwright"} else "30"

        db_host = _env("DB_HOST", "127.0.0.1") or "127.0.0.1"
        db_name = _env("DB_DATABASE") or _env("DB_NAME")
        db_user = _env("DB_USERNAME") or _env("DB_USER")
        if not db_name or not db_user:
            raise ConfigurationError("DB_DATABASE and DB_USERNAME are required")

        return cls(
            proxy=proxy,
            proxy_check_url=_env("PROXY_CHECK_URL", "https://ipv4.webshare.io/")
            or "https://ipv4.webshare.io/",
            http_backend=backend,
            http_timeout_seconds=float(_env("HTTP_TIMEOUT_SECONDS", timeout_default) or timeout_default),
            http_retries=_env_int("HTTP_RETRIES", 1),
            http_retry_delay_seconds=float(_env("HTTP_RETRY_DELAY_SECONDS", "2") or "2"),
            http_headless=(_env("HTTP_HEADLESS", "true") or "true").lower() in {"1", "true", "yes"},
            db_host=db_host,
            db_port=_env_int("DB_PORT", 3306),
            db_name=db_name,
            db_user=db_user,
            db_password=_env("DB_PASSWORD") or "",
            default_stock=_env_int("DEFAULT_STOCK", 10),
            default_user_id=_env_int("DEFAULT_USER_ID", 1),
            default_color_id=_env_int("DEFAULT_COLOR_ID", 1),
            default_brand_slug=_env("DEFAULT_BRAND_SLUG", "decathlon") or "decathlon",
        )
