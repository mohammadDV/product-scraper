from __future__ import annotations

from abc import ABC, abstractmethod

from product_scraper.models import ScrapedProduct


class SiteParser(ABC):
    """Brand/site specific HTML parser.

    Add a new site by subclassing this, then registering it in `default_registry()`.
    """

    slug: str

    @abstractmethod
    def matches(self, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def parse_product(self, html: str, url: str) -> ScrapedProduct:
        raise NotImplementedError

    def parse_product_list(self, html: str, domain: str) -> list[str]:
        raise NotImplementedError(f"{self.slug} product-list parsing is not implemented yet")
