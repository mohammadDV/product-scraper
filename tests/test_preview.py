from __future__ import annotations

from product_scraper.persistence.storage import ProductStorage
from product_scraper.scraper import ProductScraper
from product_scraper.sites.registry import default_registry
from tests.conftest import fixture_text
from tests.fakes import FakeHttpClient, InMemoryProductRepository

URL = "https://www.decathlon.com.tr/p/bileklik-sag-veya-sol-seviye-1/_/R-p-364504?mc=8941380"
CODE = "8941380"


def _scraper(settings) -> tuple[ProductScraper, InMemoryProductRepository, FakeHttpClient]:
    repo = InMemoryProductRepository()
    http = FakeHttpClient({URL: fixture_text("decathlon", "one_size.html")})
    scraper = ProductScraper(
        http=http,
        registry=default_registry(),
        storage=ProductStorage(repo, settings),
        repository=repo,
    )
    return scraper, repo, http


def test_preview_url_new_product_does_not_write(settings) -> None:
    scraper, repo, http = _scraper(settings)

    result = scraper.preview(url=URL, brand_id=2, category_id=4)

    assert result.mode == "url"
    assert result.action == "create"
    assert result.existing is None
    assert result.stored is None
    assert result.has_changes
    assert result.product.code == CODE
    assert repo.products == {}
    assert http.requested == [URL]


def test_preview_url_existing_product_shows_price_change(settings) -> None:
    scraper, repo, http = _scraper(settings)
    stored = scraper.scrape(URL, category_id=4, slug="decathlon").stored
    assert stored is not None
    repo.products[stored.id]["amount"] = 50
    http.requested.clear()

    result = scraper.preview(url=URL)

    assert result.action == "update"
    assert result.existing is not None
    assert result.existing.price == 50
    assert repo.products[stored.id]["amount"] == 50
    price_change = next(change for change in result.changes if change.field == "price")
    assert price_change.current == 50
    assert price_change.incoming == 199
    assert price_change.changed


def test_preview_code_compares_only_offer_fields(settings) -> None:
    scraper, repo, _http = _scraper(settings)
    scraper.scrape(URL, category_id=4, slug="decathlon")
    repo.products[1]["title"] = "OLD TITLE"
    repo.products[1]["amount"] = 50

    result = scraper.preview(code=CODE, brand_id=2)

    assert result.mode == "code"
    assert result.action == "refresh"
    assert {change.field for change in result.changes} == {"price", "discount", "sizes"}
    assert next(change for change in result.changes if change.field == "price").changed
    assert repo.products[1]["title"] == "OLD TITLE"
    assert repo.products[1]["amount"] == 50


def test_apply_url_persists_after_preview(settings) -> None:
    scraper, repo, _http = _scraper(settings)

    preview = scraper.preview(url=URL, brand_id=2, category_id=4, persist=False)
    assert preview.stored is None
    applied = scraper.preview(url=URL, brand_id=2, category_id=4, persist=True)

    assert applied.stored is not None
    assert applied.stored.created is True
    assert applied.action == "create"
    assert repo.products[applied.stored.id]["amount"] == 199
