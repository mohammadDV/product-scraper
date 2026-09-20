from __future__ import annotations

from typing import Protocol

from product_scraper.models import BrandRecord, EndpointRecord


class ProductRepository(Protocol):
    def get_brand_by_slug(self, slug: str) -> BrandRecord | None: ...

    def get_brand_by_id(self, brand_id: int) -> BrandRecord | None: ...

    def find_product_id_by_url(self, url: str) -> int | None: ...

    def insert_product(self, fields: dict) -> int: ...

    def update_product(self, product_id: int, fields: dict) -> None: ...

    def sync_category(self, product_id: int, category_id: int) -> None: ...

    def upsert_image(
        self,
        product_id: int,
        path: str,
        file_type: str,
        status: int,
        priority: int,
    ) -> None: ...

    def upsert_size(
        self,
        product_id: int,
        code: str,
        title: str,
        status: int,
        stock: int,
        priority: int,
    ) -> None: ...

    def insert_endpoints_if_missing(self, rows: list[dict]) -> None: ...

    def pending_endpoints(self, *, brand_slug: str | None, limit: int) -> list[EndpointRecord]: ...

    def mark_endpoint_done(self, endpoint_id: int) -> None: ...
