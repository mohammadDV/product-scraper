from __future__ import annotations

import json

from product_scraper.config import Settings
from product_scraper.models import ScrapedProduct
from product_scraper.persistence.storage import ProductStorage
from tests.fakes import InMemoryProductRepository

URL = "https://www.decathlon.com.tr/p/bileklik-sag-veya-sol-seviye-1/_/R-p-364504?mc=8941380"


def _product(**overrides) -> ScrapedProduct:
    data = dict(
        url=URL,
        title="Bileklik Sağ veya Sol - Seviye 1",
        code="8941380",
        price=199,
        discount=0,
        images=("https://img.example/1.jpg", "https://img.example/2.jpg"),
        sizes={"M 56-59cm": "inStock", "L": "low", "XL": "outOfStock"},
        related_product_ids=("8941380", "8941381", "12"),
    )
    data.update(overrides)
    return ScrapedProduct(**data)


def test_store_inserts_product_images_sizes_and_related_endpoints(settings: Settings) -> None:
    repo = InMemoryProductRepository()
    storage = ProductStorage(repo, settings)

    stored = storage.store(_product(), category_id=4, brand_id=2)

    assert stored.created is True
    row = repo.products[stored.id]
    assert row["title"] == "Bileklik Sağ veya Sol - Seviye 1"
    assert row["code"] == "8941380"
    assert row["amount"] == 199
    assert row["discount"] == 0
    assert row["status"] == "pending"
    assert row["stock"] == 10
    assert row["image"] == "https://img.example/1.jpg"
    assert row["brand_id"] == 2
    assert row["color_id"] == 1
    assert row["user_id"] == 1
    assert json.loads(row["related_products"]) == [
        "https://www.decathlon.com.tr/p/bileklik-sag-veya-sol-seviye-1/_/R-p-364504?mc=8941381",
    ]
    assert repo.categories[stored.id] == 4
    assert [image["path"] for image in repo.images] == [
        "https://img.example/1.jpg",
        "https://img.example/2.jpg",
    ]
    assert [image["priority"] for image in repo.images] == [10, 9]
    sizes = {item["code"]: item["stock"] for item in repo.sizes}
    assert sizes == {"M 56-59cm": 10, "L": 5, "XL": 0}
    assert list(repo.endpoints) == [
        "https://www.decathlon.com.tr/p/bileklik-sag-veya-sol-seviye-1/_/R-p-364504?mc=8941381",
    ]


def test_store_updates_existing_product(settings: Settings) -> None:
    repo = InMemoryProductRepository()
    storage = ProductStorage(repo, settings)
    first = storage.store(_product(price=199), category_id=4, brand_id=2)
    second = storage.store(_product(price=149, discount=25), category_id=4, brand_id=2)

    assert first.id == second.id
    assert second.created is False
    assert repo.products[second.id]["amount"] == 149
    assert repo.products[second.id]["discount"] == 25


def test_update_price_and_stock(settings: Settings) -> None:
    repo = InMemoryProductRepository()
    storage = ProductStorage(repo, settings)
    stored = storage.store(_product(), category_id=4, brand_id=2)
    storage.update_price_and_stock(
        _product(price=180, sizes={"M 56-59cm": "outOfStock"}),
        stored.id,
    )
    assert repo.products[stored.id]["amount"] == 180
    assert repo.products[stored.id]["is_failed"] == 0
    assert repo.sizes[0]["stock"] == 0
