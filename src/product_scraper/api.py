from __future__ import annotations

import os
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from product_scraper.config import Settings
from product_scraper.exceptions import (
    CloudflareBlockedError,
    HttpError,
    ParseError,
    PersistenceError,
    ProductNotFoundError,
    ScraperError,
    UnknownSiteError,
)
from product_scraper.http_client import create_http_client
from product_scraper.persistence.mysql import MySQLProductRepository
from product_scraper.persistence.storage import ProductStorage
from product_scraper.preview import preview_payload
from product_scraper.scraper import ProductScraper
from product_scraper.sites.registry import default_registry

ScraperFactory = Callable[[], ProductScraper]


class ScrapeRequest(BaseModel):
    url: str | None = None
    code: str | None = None
    brand_id: int | None = None
    category_id: int | None = None
    slug: str | None = None


class HealthResponse(BaseModel):
    status: str = Field(default="ok")


def create_scraper(settings: Settings | None = None) -> ProductScraper:
    settings = settings or Settings.from_env()
    repository = MySQLProductRepository(settings)
    return ProductScraper(
        http=create_http_client(settings),
        registry=default_registry(),
        storage=ProductStorage(repository, settings),
        repository=repository,
    )


def _status_for(exc: ScraperError) -> int:
    if isinstance(exc, ProductNotFoundError):
        return 404
    if isinstance(exc, (CloudflareBlockedError, HttpError)):
        return 502
    if isinstance(exc, (ParseError, UnknownSiteError)):
        return 422
    if isinstance(exc, PersistenceError):
        return 409
    return 400


def create_app(scraper_factory: ScraperFactory | None = None) -> FastAPI:
    factory = scraper_factory or create_scraper
    app = FastAPI(title="product-scraper", version="0.1.0")

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        expected = os.getenv("PRODUCT_SCRAPER_TOKEN", "").strip()
        if not expected or request.url.path == "/health":
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {expected}":
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)

    @app.exception_handler(ScraperError)
    async def scraper_error_handler(_request: Request, exc: ScraperError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=_status_for(exc))

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    def _run(payload: ScrapeRequest, *, persist: bool):
        scraper = factory()
        return preview_payload(
            scraper.preview(
                url=payload.url,
                code=payload.code,
                brand_id=payload.brand_id,
                slug=payload.slug,
                category_id=payload.category_id,
                persist=persist,
            )
        )

    @app.post("/preview")
    def preview(payload: ScrapeRequest) -> dict:
        return _run(payload, persist=False)

    @app.post("/apply")
    def apply(payload: ScrapeRequest) -> dict:
        return _run(payload, persist=True)

    return app


app = create_app()
