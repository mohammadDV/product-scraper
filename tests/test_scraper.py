from __future__ import annotations

from product_scraper.http_client import looks_like_cloudflare
from product_scraper.scraper import ProductScraper
from product_scraper.sites.registry import default_registry
from tests.conftest import fixture_text
from tests.fakes import FakeHttpClient, InMemoryProductRepository
from product_scraper.persistence.storage import ProductStorage

URL = "https://www.decathlon.com.tr/p/bileklik-sag-veya-sol-seviye-1/_/R-p-364504?mc=8941380"


def test_looks_like_cloudflare() -> None:
    assert looks_like_cloudflare(fixture_text("cloudflare.html"))
    assert looks_like_cloudflare("<html><head><title>Bir dakika lütfen...</title></head><body></body></html>")
    assert looks_like_cloudflare("<html><script>window._cf_chl_opt = {}</script></html>")
    assert not looks_like_cloudflare("<html><h1>Bileklik</h1></html>")


def test_scraper_persists_parsed_product(settings) -> None:
    repo = InMemoryProductRepository()
    http = FakeHttpClient({URL: fixture_text("decathlon", "one_size.html")})
    scraper = ProductScraper(
        http=http,
        registry=default_registry(),
        storage=ProductStorage(repo, settings),
        repository=repo,
    )

    result = scraper.scrape(URL, category_id=4, slug="decathlon")

    assert result.stored is not None
    assert result.product.code == "8941380"
    assert result.product.sizes == {"M 56-59cm": "inStock"}
    assert repo.products[result.stored.id]["title"] == "Bileklik Sağ veya Sol - Seviye 1"
    assert http.requested == [URL]


def test_scraper_dry_run_does_not_write(settings) -> None:
    repo = InMemoryProductRepository()
    http = FakeHttpClient({URL: fixture_text("decathlon", "one_size.html")})
    scraper = ProductScraper(
        http=http,
        registry=default_registry(),
        storage=ProductStorage(repo, settings),
        repository=repo,
    )

    result = scraper.scrape(URL, category_id=4, persist=False)

    assert result.stored is None
    assert repo.products == {}


def test_process_endpoint_marks_done(settings) -> None:
    repo = InMemoryProductRepository()
    repo.endpoints[URL] = {"url": URL, "brand_id": 2, "category_id": 4, "status": 0}
    http = FakeHttpClient({URL: fixture_text("decathlon", "one_size.html")})
    scraper = ProductScraper(
        http=http,
        registry=default_registry(),
        storage=ProductStorage(repo, settings),
        repository=repo,
    )
    endpoint = repo.pending_endpoints(brand_slug="decathlon", limit=1)[0]
    result = scraper.process_endpoint(endpoint)
    assert result.stored is not None
    assert endpoint.id in repo.done_endpoints
