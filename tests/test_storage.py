from __future__ import annotations

import copy
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
    repo.products[stored.id]["is_failed"] = 1
    original_title = repo.products[stored.id]["title"]
    original_image = repo.products[stored.id]["image"]
    original_images = copy.deepcopy(repo.images)
    original_category = repo.categories[stored.id]
    original_endpoints = list(repo.endpoints)

    updated = storage.update_price_and_stock(
        _product(
            title="Should not persist",
            price=180,
            discount=15,
            images=("https://img.example/changed.jpg",),
            sizes={"M 56-59cm": "outOfStock", "L": "inStock"},
        ),
        stored.id,
    )

    row = repo.products[stored.id]
    assert updated.created is False
    assert row["amount"] == 180
    assert row["discount"] == 15
    assert row["title"] == original_title
    assert row["image"] == original_image
    assert row["is_failed"] == 1
    assert row["status"] == "pending"
    assert repo.images == original_images
    assert repo.categories[stored.id] == original_category
    assert list(repo.endpoints) == original_endpoints
    sizes = {item["code"]: item["stock"] for item in repo.sizes}
    assert sizes["M 56-59cm"] == 0
    assert sizes["L"] == 10


def test_find_product_by_code_optionally_filters_brand(settings: Settings) -> None:
    repo = InMemoryProductRepository()
    storage = ProductStorage(repo, settings)
    stored = storage.store(_product(), category_id=4, brand_id=2)

    found = repo.find_product_by_code("8941380")
    assert found is not None
    assert found.id == stored.id
    assert found.brand_id == 2
    assert found.url == URL
    assert repo.find_product_by_code("8941380", brand_id=2) is not None
    assert repo.find_product_by_code("8941380", brand_id=99) is None
    assert repo.find_product_by_code("missing") is None
