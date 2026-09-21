from __future__ import annotations

from dataclasses import dataclass

from product_scraper.exceptions import PersistenceError, ProductNotFoundError, ScraperError
from product_scraper.http_client import HttpClient
from product_scraper.models import EndpointRecord, ExistingProduct, PreviewResult, ScrapedProduct, StoredProduct
from product_scraper.persistence.repository import ProductRepository
from product_scraper.persistence.storage import ProductStorage
from product_scraper.preview import diff_fields
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

    def preview(
        self,
        *,
        url: str | None = None,
        code: str | None = None,
        brand_id: int | None = None,
        slug: str | None = None,
        category_id: int | None = None,
        persist: bool = False,
    ) -> PreviewResult:
        """Fetch a product and compare it with the catalog. Persist only when asked."""
        normalized_url = (url or "").strip() or None
        normalized_code = (code or "").strip() or None
        if bool(normalized_url) == bool(normalized_code):
            raise ScraperError("Provide either a URL or code")

        if normalized_code:
            return self._preview_by_code(
                normalized_code,
                brand_id=brand_id,
                slug=slug,
                persist=persist,
            )

        product = self.fetch_and_parse(normalized_url, slug)
        product_id = self._repository.find_product_id_by_url(product.url)
        existing = self._repository.get_catalog_product(product_id) if product_id else None
        action = "update" if existing else "create"
        changes = self._changes(product, existing, action)
        stored = None
        if persist:
            if category_id is None:
                raise ScraperError("category_id is required to save a product from URL")
            parser = self._registry.resolve(normalized_url, slug)
            resolved_brand_id = self._storage.resolve_brand_id(brand_id=brand_id, slug=parser.slug)
            stored = self._storage.store(
                product,
                category_id=category_id,
                brand_id=resolved_brand_id,
            )
        return PreviewResult(
            mode="url",
            action=action,
            product=product,
            existing=existing,
            changes=changes,
            stored=stored,
        )

    def _preview_by_code(
        self,
        code: str,
        *,
        brand_id: int | None,
        slug: str | None,
        persist: bool,
    ) -> PreviewResult:
        existing_row = self._require_existing_product(code, brand_id=brand_id, slug=slug)
        brand = self._repository.get_brand_by_id(existing_row.brand_id)
        if brand is None:
            raise PersistenceError(f"Brand not found for id {existing_row.brand_id}")
        if not existing_row.url:
            raise PersistenceError(f"Product {code!r} has no URL")
        self._registry.get(brand.slug)

        existing = self._repository.get_catalog_product(existing_row.id)
        product = self.fetch_and_parse(existing_row.url, slug=brand.slug)
        stored = None
        if persist:
            stored = self._storage.update_price_and_stock(product, existing_row.id)
        return PreviewResult(
            mode="code",
            action="refresh",
            product=product,
            existing=existing,
            changes=self._changes(product, existing, "refresh"),
            stored=stored,
        )

    def _changes(self, product: ScrapedProduct, existing, action: str) -> tuple:
        return diff_fields(
            product,
            existing,
            action=action,
            default_stock=self._storage._settings.default_stock,
        )

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
