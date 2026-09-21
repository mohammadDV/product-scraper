from __future__ import annotations

import copy

import pytest

from product_scraper.exceptions import PersistenceError, ProductNotFoundError, UnknownSiteError
from product_scraper.http_client import looks_like_cloudflare
from product_scraper.models import BrandRecord
from product_scraper.persistence.storage import ProductStorage
from product_scraper.scraper import ProductScraper
from product_scraper.sites.registry import default_registry
from tests.conftest import fixture_text
from tests.fakes import FakeHttpClient, InMemoryProductRepository

URL = "https://www.decathlon.com.tr/p/bileklik-sag-veya-sol-seviye-1/_/R-p-364504?mc=8941380"
CODE = "8941380"


def _scraper(settings, repo=None, pages=None) -> tuple[ProductScraper, InMemoryProductRepository, FakeHttpClient]:
    repo = repo or InMemoryProductRepository()
    http = FakeHttpClient(pages or {URL: fixture_text("decathlon", "one_size.html")})
    scraper = ProductScraper(
        http=http,
        registry=default_registry(),
        storage=ProductStorage(repo, settings),
        repository=repo,
    )
    return scraper, repo, http


def test_looks_like_cloudflare() -> None:
    assert looks_like_cloudflare(fixture_text("cloudflare.html"))
    assert looks_like_cloudflare("<html><head><title>Bir dakika lütfen...</title></head><body></body></html>")
    assert looks_like_cloudflare("<html><script>window._cf_chl_opt = {}</script></html>")
    assert not looks_like_cloudflare("<html><h1>Bileklik</h1></html>")


def test_scraper_persists_parsed_product(settings) -> None:
    scraper, repo, http = _scraper(settings)

    result = scraper.scrape(URL, category_id=4, slug="decathlon")

    assert result.stored is not None
    assert result.product.code == CODE
    assert result.product.sizes == {"M 56-59cm": "inStock"}
    assert repo.products[result.stored.id]["title"] == "Bileklik Sağ veya Sol - Seviye 1"
    assert http.requested == [URL]


def test_scraper_dry_run_does_not_write(settings) -> None:
    scraper, repo, _http = _scraper(settings)

    result = scraper.scrape(URL, category_id=4, persist=False)

    assert result.stored is None
    assert repo.products == {}


def test_process_endpoint_marks_done(settings) -> None:
    scraper, repo, _http = _scraper(settings)
    repo.endpoints[URL] = {"url": URL, "brand_id": 2, "category_id": 4, "status": 0}
    endpoint = repo.pending_endpoints(brand_slug="decathlon", limit=1)[0]
    result = scraper.process_endpoint(endpoint)
    assert result.stored is not None
    assert endpoint.id in repo.done_endpoints


def test_refresh_by_code_updates_only_offer_fields(settings) -> None:
    scraper, repo, http = _scraper(settings)
    stored = scraper._storage.store(
        scraper.fetch_and_parse(URL, "decathlon"),
        category_id=4,
        brand_id=2,
    )
    http.requested.clear()
    row = repo.products[stored.id]
    row.update(
        {
            "title": "OLD TITLE",
            "amount": 50,
            "discount": 10,
            "image": "https://old.example/image.jpg",
            "status": "pending",
            "is_failed": 1,
            "description": "keep me",
        }
    )
    original_images = copy.deepcopy(repo.images)
    original_endpoints = list(repo.endpoints)
    original_category = repo.categories[stored.id]
    original_count = len(repo.products)

    result = scraper.refresh_by_code(CODE)

    assert result.stored is not None
    assert result.stored.created is False
    assert result.stored.id == stored.id
    assert len(repo.products) == original_count
    assert http.requested == [URL]
    updated = repo.products[stored.id]
    assert updated["amount"] == 199
    assert updated["discount"] == 0
    assert updated["title"] == "OLD TITLE"
    assert updated["image"] == "https://old.example/image.jpg"
    assert updated["status"] == "pending"
    assert updated["is_failed"] == 1
    assert updated["description"] == "keep me"
    assert repo.images == original_images
    assert list(repo.endpoints) == original_endpoints
    assert repo.categories[stored.id] == original_category
    sizes = {item["code"]: item["stock"] for item in repo.sizes if item["product_id"] == stored.id}
    assert sizes["M 56-59cm"] == 10


def test_refresh_by_code_missing_product_does_not_fetch_or_create(settings) -> None:
    scraper, repo, http = _scraper(settings)

    with pytest.raises(ProductNotFoundError, match="محصول موجود نیست") as exc:
        scraper.refresh_by_code("999999")

    assert exc.value.code == "999999"
    assert http.requested == []
    assert repo.products == {}


def test_refresh_by_code_dry_run_fetches_but_does_not_write(settings) -> None:
    scraper, repo, http = _scraper(settings)
    stored = scraper._storage.store(
        scraper.fetch_and_parse(URL, "decathlon"),
        category_id=4,
        brand_id=2,
    )
    repo.products[stored.id]["amount"] = 50
    http.requested.clear()

    result = scraper.refresh_by_code(CODE, persist=False)

    assert result.stored is None
    assert result.product.price == 199
    assert repo.products[stored.id]["amount"] == 50
    assert http.requested == [URL]


def test_refresh_by_code_uses_product_brand_id_for_parser(settings) -> None:
    scraper, repo, http = _scraper(settings)
    scraper._storage.store(
        scraper.fetch_and_parse(URL, "decathlon"),
        category_id=4,
        brand_id=2,
    )
    repo.brands["other"] = BrandRecord(id=99, slug="other", domain="https://other.example")
    product_id = repo.find_product_id_by_url(URL)
    assert product_id is not None
    repo.products[product_id]["brand_id"] = 99
    http.requested.clear()

    with pytest.raises(UnknownSiteError):
        scraper.refresh_by_code(CODE)

    assert http.requested == []


def test_refresh_by_code_filters_lookup_by_brand_id(settings) -> None:
    scraper, repo, http = _scraper(settings)
    scraper._storage.store(
        scraper.fetch_and_parse(URL, "decathlon"),
        category_id=4,
        brand_id=2,
    )
    http.requested.clear()

    with pytest.raises(ProductNotFoundError):
        scraper.refresh_by_code(CODE, brand_id=99)

    assert http.requested == []
    scraper.refresh_by_code(CODE, brand_id=2)
    assert http.requested == [URL]


def test_refresh_by_code_filters_lookup_by_slug(settings) -> None:
    scraper, repo, http = _scraper(settings)
    scraper._storage.store(
        scraper.fetch_and_parse(URL, "decathlon"),
        category_id=4,
        brand_id=2,
    )
    repo.brands["adidas"] = BrandRecord(id=3, slug="adidas", domain="https://www.adidas.com.tr")
    http.requested.clear()

    with pytest.raises(ProductNotFoundError):
        scraper.refresh_by_code(CODE, slug="adidas")
    assert http.requested == []

    scraper.refresh_by_code(CODE, slug="decathlon")
    assert http.requested == [URL]


def test_refresh_by_code_blank_code_does_not_fetch(settings) -> None:
    scraper, _repo, http = _scraper(settings)
    with pytest.raises(ProductNotFoundError):
        scraper.refresh_by_code("   ")
    assert http.requested == []


def test_refresh_by_code_requires_url(settings) -> None:
    scraper, repo, http = _scraper(settings)
    repo.insert_product({"url": "", "code": CODE, "brand_id": 2, "title": "no url", "amount": 1})
    with pytest.raises(PersistenceError, match="has no URL"):
        scraper.refresh_by_code(CODE)
    assert http.requested == []
