from __future__ import annotations

import pytest

from product_scraper.cli import build_parser, execute_scrape
from product_scraper.exceptions import ProductNotFoundError, ScraperError
from product_scraper.persistence.storage import ProductStorage
from product_scraper.scraper import ProductScraper
from product_scraper.sites.registry import default_registry
from tests.conftest import fixture_text
from tests.fakes import FakeHttpClient, InMemoryProductRepository

URL = "https://www.decathlon.com.tr/p/bileklik-sag-veya-sol-seviye-1/_/R-p-364504?mc=8941380"
CODE = "8941380"


def _scraper(settings) -> tuple[ProductScraper, InMemoryProductRepository]:
    repo = InMemoryProductRepository()
    http = FakeHttpClient({URL: fixture_text("decathlon", "one_size.html")})
    scraper = ProductScraper(
        http=http,
        registry=default_registry(),
        storage=ProductStorage(repo, settings),
        repository=repo,
    )
    return scraper, repo


def test_parser_accepts_code_without_url() -> None:
    args = build_parser().parse_args(["scrape", "--code", CODE])
    assert args.command == "scrape"
    assert args.code == CODE
    assert args.url is None
    assert args.dry_run is False


def test_parser_url_mode_still_works() -> None:
    args = build_parser().parse_args(["scrape", URL, "--category-id", "4"])
    assert args.url == URL
    assert args.code is None
    assert args.category_id == 4


def test_execute_scrape_requires_url_or_code(settings) -> None:
    scraper, _repo = _scraper(settings)
    args = build_parser().parse_args(["scrape", "--dry-run"])
    with pytest.raises(ScraperError, match="Provide either a URL or --code"):
        execute_scrape(scraper, args)


def test_execute_scrape_rejects_url_and_code_together(settings) -> None:
    scraper, _repo = _scraper(settings)
    args = build_parser().parse_args(["scrape", URL, "--code", CODE])
    with pytest.raises(ScraperError, match="Provide either a URL or --code"):
        execute_scrape(scraper, args)


def test_execute_scrape_code_does_not_require_category_id(settings) -> None:
    scraper, repo = _scraper(settings)
    product = scraper.fetch_and_parse(URL, "decathlon")
    stored = scraper._storage.store(product, category_id=4, brand_id=2)
    repo.products[stored.id]["amount"] = 50

    args = build_parser().parse_args(["scrape", "--code", CODE])
    result = execute_scrape(scraper, args)

    assert result.stored is not None
    assert result.stored.created is False
    assert result.stored.id == stored.id
    assert repo.products[stored.id]["amount"] == 199
    assert len(repo.products) == 1


def test_execute_scrape_code_missing_product(settings) -> None:
    scraper, repo = _scraper(settings)
    args = build_parser().parse_args(["scrape", "--code", "missing"])
    with pytest.raises(ProductNotFoundError, match="محصول موجود نیست"):
        execute_scrape(scraper, args)
    assert repo.products == {}


def test_execute_scrape_url_still_requires_category_id(settings) -> None:
    scraper, _repo = _scraper(settings)
    args = build_parser().parse_args(["scrape", URL])
    with pytest.raises(ScraperError, match="--category-id is required"):
        execute_scrape(scraper, args)
