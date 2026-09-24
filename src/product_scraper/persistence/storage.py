from __future__ import annotations

import json
from datetime import datetime

from product_scraper.config import Settings
from product_scraper.exceptions import PersistenceError
from product_scraper.models import ScrapedProduct, StoredProduct
from product_scraper.persistence.repository import ProductRepository
from product_scraper.sites.decathlon import stock_from_status


class ProductStorage:
    """Maps scraped data onto the Laravel product tables."""

    def __init__(self, repository: ProductRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def store(
        self,
        product: ScrapedProduct,
        *,
        category_id: int,
        brand_id: int,
    ) -> StoredProduct:
        related_urls = product.related_urls()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fields = {
            "title": product.title,
            "code": product.code or None,
            "description": "",
            "details": "",
            "amount": product.price,
            "discount": product.discount,
            "image": product.images[0] if product.images else None,
            "status": "pending",
            "vip": 0,
            "priority": 1,
            "color_id": self._settings.default_color_id,
            "brand_id": brand_id,
            "user_id": self._settings.default_user_id,
            "related_products": json.dumps(related_urls, ensure_ascii=False) if related_urls else None,
            "url": product.url,
            "updated_at": now,
        }

        product_id = self._repository.find_product_id_by_url(product.url)
        created = product_id is None
        if product_id is None:
            fields["created_at"] = now
            product_id = self._repository.insert_product(fields)
        else:
            self._repository.update_product(product_id, fields)

        self._repository.sync_category(product_id, category_id)
        self._sync_images(product_id, product.images)
        self._sync_sizes(product_id, product.sizes)
        self._insert_related_endpoints(related_urls, brand_id=brand_id, category_id=category_id)
        return StoredProduct(id=product_id, url=product.url, created=created)

    def update_price_and_stock(self, product: ScrapedProduct, product_id: int) -> StoredProduct:
        """Update only price, discount, and sizes. Never creates a product or touches other fields."""
        self._repository.update_product(
            product_id,
            {
                "amount": product.price,
                "discount": product.discount,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        self._sync_sizes(product_id, product.sizes)
        return StoredProduct(id=product_id, url=product.url, created=False)

    def resolve_brand_id(self, *, brand_id: int | None, slug: str) -> int:
        if brand_id is not None:
            return brand_id
        brand = self._repository.get_brand_by_slug(slug)
        if brand is None:
            raise PersistenceError(f"Brand not found for slug {slug!r}")
        return brand.id

    def _sync_images(self, product_id: int, images: tuple[str, ...]) -> None:
        for index, path in enumerate(images):
            self._repository.upsert_image(
                product_id=product_id,
                path=path,
                file_type="image",
                status=1,
                priority=10 - index,
            )

    def _sync_sizes(self, product_id: int, sizes: dict[str, str]) -> None:
        priority = 100
        for title, status in sizes.items():
            size_title = title.strip(".")
            self._repository.upsert_size(
                product_id=product_id,
                code=size_title,
                title=size_title,
                status=1,
                stock=stock_from_status(status, self._settings.default_stock),
                priority=priority,
            )
            priority -= 1

    def _insert_related_endpoints(
        self,
        related_urls: list[str],
        *,
        brand_id: int,
        category_id: int,
    ) -> None:
        rows = [
            {
                "url": url,
                "brand_id": brand_id,
                "category_id": category_id,
                "status": 0,
            }
            for url in related_urls
        ]
        self._repository.insert_endpoints_if_missing(rows)
