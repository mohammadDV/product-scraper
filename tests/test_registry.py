from __future__ import annotations

import pytest

from product_scraper.exceptions import UnknownSiteError
from product_scraper.sites.base import SiteParser
from product_scraper.sites.decathlon import DecathlonParser
from product_scraper.sites.registry import SiteRegistry, default_registry


class DummyParser(SiteParser):
    slug = "dummy"

    def matches(self, url: str) -> bool:
        return "dummy.example" in url

    def parse_product(self, html: str, url: str):
        raise NotImplementedError


def test_default_registry_has_decathlon() -> None:
    registry = default_registry()
    assert registry.get("decathlon").slug == "decathlon"
    parser = registry.resolve("https://www.decathlon.com.tr/p/foo")
    assert isinstance(parser, DecathlonParser)


def test_registry_can_add_another_site() -> None:
    registry = SiteRegistry([DecathlonParser(), DummyParser()])
    assert registry.resolve("https://dummy.example/p/1").slug == "dummy"
    assert registry.slugs() == ["decathlon", "dummy"]


def test_unknown_site() -> None:
    registry = default_registry()
    with pytest.raises(UnknownSiteError):
        registry.resolve("https://www.adidas.com.tr/p/foo")
