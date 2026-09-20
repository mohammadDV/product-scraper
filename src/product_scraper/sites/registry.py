from __future__ import annotations

from collections.abc import Iterable

from product_scraper.exceptions import UnknownSiteError
from product_scraper.sites.base import SiteParser
from product_scraper.sites.decathlon import DecathlonParser


class SiteRegistry:
    def __init__(self, parsers: Iterable[SiteParser]) -> None:
        self._parsers = list(parsers)
        self._by_slug = {parser.slug: parser for parser in self._parsers}

    def get(self, slug: str) -> SiteParser:
        parser = self._by_slug.get(slug.lower())
        if parser is None:
            raise UnknownSiteError(url="", slug=slug)
        return parser

    def resolve(self, url: str, slug: str | None = None) -> SiteParser:
        if slug:
            return self.get(slug)
        for parser in self._parsers:
            if parser.matches(url):
                return parser
        raise UnknownSiteError(url)

    def slugs(self) -> list[str]:
        return [parser.slug for parser in self._parsers]


def default_registry() -> SiteRegistry:
    return SiteRegistry(
        [
            DecathlonParser(),
        ]
    )
