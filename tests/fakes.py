from __future__ import annotations

from datetime import datetime

from product_scraper.models import BrandRecord, CatalogProduct, EndpointRecord, ExistingProduct


class InMemoryProductRepository:
    def __init__(self) -> None:
        self.brands: dict[str, BrandRecord] = {
            "decathlon": BrandRecord(id=2, slug="decathlon", domain="https://www.decathlon.com.tr"),
        }
        self.products: dict[int, dict] = {}
        self.products_by_url: dict[str, int] = {}
        self.categories: dict[int, int] = {}
        self.images: list[dict] = []
        self.sizes: list[dict] = []
        self.stocks: dict[int, dict] = {}
        self.inventory_transactions: list[dict] = []
        self.endpoints: dict[str, dict] = {}
        self.done_endpoints: list[int] = []
        self._next_id = 1
        self._next_size_id = 1
        self._next_inventory_transaction_id = 1

    def get_brand_by_slug(self, slug: str) -> BrandRecord | None:
        return self.brands.get(slug)

    def get_brand_by_id(self, brand_id: int) -> BrandRecord | None:
        for brand in self.brands.values():
            if brand.id == brand_id:
                return brand
        return None

    def find_product_id_by_url(self, url: str) -> int | None:
        return self.products_by_url.get(url)

    def find_product_by_code(self, code: str, *, brand_id: int | None = None) -> ExistingProduct | None:
        for product_id, row in self.products.items():
            if str(row.get("code") or "") != str(code):
                continue
            if brand_id is not None and row.get("brand_id") != brand_id:
                continue
            return ExistingProduct(
                id=product_id,
                url=row.get("url") or "",
                code=str(row.get("code") or ""),
                brand_id=int(row["brand_id"]),
            )
        return None

    def get_catalog_product(self, product_id: int) -> CatalogProduct | None:
        row = self.products.get(product_id)
        if row is None:
            return None
        images = tuple(item["path"] for item in self.images if item["product_id"] == product_id)
        sizes = {
            str(item["code"]): int(self.stocks.get(int(item["id"]), {}).get("quantity", 0))
            for item in self.sizes
            if item["product_id"] == product_id
        }
        return CatalogProduct(
            id=product_id,
            url=row.get("url") or "",
            title=row.get("title") or "",
            code=str(row.get("code") or ""),
            price=int(row.get("amount") or 0),
            discount=int(row.get("discount") or 0),
            brand_id=int(row.get("brand_id") or 0),
            category_id=self.categories.get(product_id),
            images=images,
            sizes=sizes,
        )

    def insert_product(self, fields: dict) -> int:
        product_id = self._next_id
        self._next_id += 1
        self.products[product_id] = dict(fields)
        self.products_by_url[fields["url"]] = product_id
        return product_id

    def update_product(self, product_id: int, fields: dict) -> None:
        payload = dict(fields)
        payload["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.products[product_id].update(payload)
        if "url" in payload:
            self.products_by_url[payload["url"]] = product_id

    def sync_category(self, product_id: int, category_id: int) -> None:
        self.categories[product_id] = category_id

    def upsert_image(
        self,
        product_id: int,
        path: str,
        file_type: str,
        status: int,
        priority: int,
    ) -> None:
        for row in self.images:
            if row["product_id"] == product_id and row["path"] == path and row["type"] == file_type:
                row.update({"status": status, "priority": priority})
                return
        self.images.append(
            {
                "product_id": product_id,
                "path": path,
                "type": file_type,
                "status": status,
                "priority": priority,
            }
        )

    def upsert_size(
        self,
        product_id: int,
        code: str,
        title: str,
        status: int,
        stock: int,
        priority: int,
    ) -> None:
        for row in self.sizes:
            if row["product_id"] == product_id and row["code"] == code:
                row.update({"title": title, "status": status, "priority": priority})
                size_id = int(row["id"])
                previous_quantity = int(self.stocks.get(size_id, {}).get("quantity", 0))
                resulting_quantity = int(stock)
                self.stocks[size_id] = {
                    "size_id": size_id,
                    "reserved": 0,
                    "quantity": resulting_quantity,
                }
                self._record_inventory_transaction(
                    product_id=product_id,
                    size_id=size_id,
                    previous_quantity=previous_quantity,
                    resulting_quantity=resulting_quantity,
                )
                return
        size_id = self._next_size_id
        self._next_size_id += 1
        self.sizes.append(
            {
                "id": size_id,
                "product_id": product_id,
                "code": code,
                "title": title,
                "status": status,
                "priority": priority,
            }
        )
        previous_quantity = 0
        resulting_quantity = int(stock)
        self.stocks[size_id] = {
            "size_id": size_id,
            "reserved": 0,
            "quantity": resulting_quantity,
        }
        self._record_inventory_transaction(
            product_id=product_id,
            size_id=size_id,
            previous_quantity=previous_quantity,
            resulting_quantity=resulting_quantity,
        )

    def _record_inventory_transaction(
        self,
        *,
        product_id: int,
        size_id: int,
        previous_quantity: int,
        resulting_quantity: int,
    ) -> None:
        quantity_change = resulting_quantity - previous_quantity
        if quantity_change == 0:
            return
        self.inventory_transactions.append(
            {
                "id": self._next_inventory_transaction_id,
                "product_id": product_id,
                "size_id": size_id,
                "type": "adjust",
                "source": "scraper",
                "user_id": None,
                "quantity_change": quantity_change,
                "previous_quantity": previous_quantity,
                "resulting_quantity": resulting_quantity,
                "description": "scraper upsert_size",
            }
        )
        self._next_inventory_transaction_id += 1

    def insert_endpoints_if_missing(self, rows: list[dict]) -> None:
        for row in rows:
            self.endpoints.setdefault(row["url"], dict(row))

    def pending_endpoints(self, *, brand_slug: str | None, limit: int) -> list[EndpointRecord]:
        items = []
        for index, (url, row) in enumerate(self.endpoints.items(), start=1):
            if row.get("status", 0) != 0:
                continue
            brand = self.get_brand_by_id(row["brand_id"])
            if brand_slug and (brand is None or brand.slug != brand_slug):
                continue
            items.append(
                EndpointRecord(
                    id=index,
                    url=url,
                    brand_id=row["brand_id"],
                    category_id=row["category_id"],
                    brand_slug=brand.slug if brand else "",
                    brand_domain=brand.domain if brand else "",
                )
            )
            if len(items) >= limit:
                break
        return items

    def mark_endpoint_done(self, endpoint_id: int) -> None:
        self.done_endpoints.append(endpoint_id)


class FakeHttpClient:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url: str) -> str:
        self.requested.append(url)
        if url not in self.pages:
            raise KeyError(url)
        return self.pages[url]
