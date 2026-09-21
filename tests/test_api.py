from __future__ import annotations

from fastapi.testclient import TestClient

from product_scraper.api import create_app
from product_scraper.persistence.storage import ProductStorage
from product_scraper.scraper import ProductScraper
from product_scraper.sites.registry import default_registry
from tests.conftest import fixture_text
from tests.fakes import FakeHttpClient, InMemoryProductRepository

URL = "https://www.decathlon.com.tr/p/bileklik-sag-veya-sol-seviye-1/_/R-p-364504?mc=8941380"
CODE = "8941380"


def _client(settings) -> tuple[TestClient, InMemoryProductRepository]:
    repo = InMemoryProductRepository()
    http = FakeHttpClient({URL: fixture_text("decathlon", "one_size.html")})
    scraper = ProductScraper(
        http=http,
        registry=default_registry(),
        storage=ProductStorage(repo, settings),
        repository=repo,
    )
    app = create_app(scraper_factory=lambda: scraper)
    return TestClient(app), repo


def test_health() -> None:
    app = create_app(scraper_factory=lambda: None)  # type: ignore[arg-type,return-value]
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_preview_url_endpoint(settings) -> None:
    client, repo = _client(settings)

    response = client.post("/preview", json={"url": URL, "brand_id": 2, "category_id": 4})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "url"
    assert body["action"] == "create"
    assert body["has_changes"] is True
    assert body["product"]["code"] == CODE
    assert body["existing"] is None
    assert repo.products == {}


def test_apply_url_endpoint_requires_category(settings) -> None:
    client, repo = _client(settings)

    response = client.post("/apply", json={"url": URL, "brand_id": 2})

    assert response.status_code == 400
    assert "category_id" in response.json()["error"]
    assert repo.products == {}


def test_apply_url_endpoint_persists(settings) -> None:
    client, repo = _client(settings)

    response = client.post("/apply", json={"url": URL, "brand_id": 2, "category_id": 4})

    assert response.status_code == 200
    body = response.json()
    assert body["stored"]["created"] is True
    assert body["product"]["code"] == CODE
    assert len(repo.products) == 1


def test_preview_missing_code(settings) -> None:
    client, _repo = _client(settings)

    response = client.post("/preview", json={"code": "missing", "brand_id": 2})

    assert response.status_code == 404
    assert response.json()["error"] == "محصول موجود نیست"
