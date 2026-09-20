from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urlparse

from product_scraper.exceptions import ConfigurationError


@dataclass(frozen=True)
class ProxySettings:
    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    def is_configured(self) -> bool:
        return bool(self.host)

    def url(self) -> str | None:
        if not self.is_configured():
            return None
        auth = ""
        if self.username:
            user = quote(self.username, safe="")
            password = quote(self.password or "", safe="")
            auth = f"{user}:{password}@"
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    def httpx_proxy(self) -> str | None:
        return self.url()

    def playwright_proxy(self) -> dict[str, str] | None:
        if not self.is_configured():
            return None
        config = {"server": f"{self.scheme}://{self.host}:{self.port}"}
        if self.username:
            config["username"] = self.username
            config["password"] = self.password or ""
        return config

    def __repr__(self) -> str:
        user = self.username or ""
        return (
            f"ProxySettings(scheme={self.scheme!r}, host={self.host!r}, "
            f"port={self.port}, username={user!r}, password={'***' if self.password else None})"
        )


def parse_proxy_url(raw: str) -> ProxySettings:
    parsed = urlparse(raw)
    if not parsed.hostname:
        raise ConfigurationError("PROXY_URL is missing a host")
    scheme = parsed.scheme or "http"
    port = parsed.port or (443 if scheme == "https" else 80)
    return ProxySettings(
        scheme=scheme,
        host=parsed.hostname,
        port=port,
        username=parsed.username,
        password=parsed.password,
    )
