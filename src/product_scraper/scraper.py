from __future__ import annotations

from dataclasses import dataclass

from product_scraper.exceptions import PersistenceError
from product_scraper.http_client import HttpClient
from product_scraper.models import EndpointRecord, ScrapedProduct, StoredProduct
from product_scraper.persistence.repository import ProductRepository
from product_scraper.persistence.storage import ProductStorage
from product_scraper.sites.registry import SiteRegistry


@dataclass(frozen=True)
class ScrapeResult:
    product: ScrapedProduct
    stored: StoredProduct | None


class ProductScraper:
    def __init__(
        self,
        http: HttpClient,
        registry: SiteRegistry,
        storage: ProductStorage,
        repository: ProductRepository,
    ) -> None:
        self._http = http
        self._registry = registry
        self._storage = storage
        self._repository = repository

    def fetch_and_parse(self, url: str, slug: str | None = None) -> ScrapedProduct:
        html = self._http.get(url)
        parser = self._registry.resolve(url, slug)
        return parser.parse_product(html, url)

    def scrape(
        self,
        url: str,
        *,
        category_id: int,
        brand_id: int | None = None,
        slug: str | None = None,
        persist: bool = True,
    ) -> ScrapeResult:
        product = self.fetch_and_parse(url, slug)
        if not persist:
            return ScrapeResult(product=product, stored=None)

        parser = self._registry.resolve(url, slug)
        resolved_brand_id = self._storage.resolve_brand_id(
            brand_id=brand_id,
            slug=parser.slug,
        )
        stored = self._storage.store(
            product,
            category_id=category_id,
            brand_id=resolved_brand_id,
        )
        return ScrapeResult(product=product, stored=stored)

    def process_endpoint(self, endpoint: EndpointRecord) -> ScrapeResult:
        result = self.scrape(
            endpoint.url,
            category_id=endpoint.category_id,
            brand_id=endpoint.brand_id,
            slug=endpoint.brand_slug,
            persist=True,
        )
        if result.stored is None:
            raise PersistenceError(f"Failed to store {endpoint.url}")
        self._repository.mark_endpoint_done(endpoint.id)
        return result
