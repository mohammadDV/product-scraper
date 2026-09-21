from __future__ import annotations

from dataclasses import dataclass

from product_scraper.exceptions import PersistenceError, ProductNotFoundError
from product_scraper.http_client import HttpClient
from product_scraper.models import EndpointRecord, ExistingProduct, ScrapedProduct, StoredProduct
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

    def refresh_by_code(
        self,
        code: str,
        *,
        brand_id: int | None = None,
        slug: str | None = None,
        persist: bool = True,
    ) -> ScrapeResult:
        """Fetch an existing catalog product and update only price, discount, and sizes.

        Looks the product up first. If it is missing, nothing is fetched or created.
        Parser selection always follows the stored product's brand_id.
        """
        existing = self._require_existing_product(code, brand_id=brand_id, slug=slug)
        brand = self._repository.get_brand_by_id(existing.brand_id)
        if brand is None:
            raise PersistenceError(f"Brand not found for id {existing.brand_id}")
        if not existing.url:
            raise PersistenceError(f"Product {code!r} has no URL")
        self._registry.get(brand.slug)

        product = self.fetch_and_parse(existing.url, slug=brand.slug)
        if not persist:
            return ScrapeResult(product=product, stored=None)

        stored = self._storage.update_price_and_stock(product, existing.id)
        return ScrapeResult(product=product, stored=stored)

    def _require_existing_product(
        self,
        code: str,
        *,
        brand_id: int | None = None,
        slug: str | None = None,
    ) -> ExistingProduct:
        normalized = (code or "").strip()
        if not normalized:
            raise ProductNotFoundError(code)

        lookup_brand_id = brand_id
        if lookup_brand_id is None and slug:
            brand = self._repository.get_brand_by_slug(slug)
            if brand is None:
                raise PersistenceError(f"Brand not found for slug {slug!r}")
            lookup_brand_id = brand.id

        existing = self._repository.find_product_by_code(normalized, brand_id=lookup_brand_id)
        if existing is None:
            raise ProductNotFoundError(normalized)
        return existing

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
