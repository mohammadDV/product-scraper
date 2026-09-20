from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from product_scraper.config import Settings
from product_scraper.exceptions import ScraperError
from product_scraper.http_client import create_http_client
from product_scraper.persistence.mysql import MySQLProductRepository
from product_scraper.persistence.storage import ProductStorage
from product_scraper.scraper import ProductScraper, ScrapeResult
from product_scraper.sites.registry import default_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape products through a configurable proxy")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-proxy", help="Fetch PROXY_CHECK_URL through the configured proxy")

    scrape = sub.add_parser("scrape", help="Scrape one product URL")
    scrape.add_argument("url")
    scrape.add_argument("--brand", dest="slug", default=None, help="Parser slug, e.g. decathlon")
    scrape.add_argument("--brand-id", type=int, default=None)
    scrape.add_argument("--category-id", type=int, default=None)
    scrape.add_argument("--dry-run", action="store_true", help="Parse only, do not write to the database")

    run = sub.add_parser("run", help="Process pending rows from the endpoints table")
    run.add_argument("--brand", dest="slug", default=None)
    run.add_argument("--limit", type=int, default=10)
    return parser


def _app(settings: Settings) -> tuple[ProductScraper, MySQLProductRepository]:
    repository = MySQLProductRepository(settings)
    scraper = ProductScraper(
        http=create_http_client(settings),
        registry=default_registry(),
        storage=ProductStorage(repository, settings),
        repository=repository,
    )
    return scraper, repository


def _print_product(result: ScrapeResult) -> None:
    payload = asdict(result.product)
    if result.stored:
        payload["stored_id"] = result.stored.id
        payload["created"] = result.stored.created
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        if args.command == "check-proxy":
            from product_scraper.http_client import HttpxClient

            html = HttpxClient(settings).get(settings.proxy_check_url)
            print(html.strip())
            return 0

        scraper, repository = _app(settings)
        if args.command == "scrape":
            persist = not args.dry_run
            if persist and args.category_id is None:
                raise ScraperError("--category-id is required unless --dry-run is set")
            result = scraper.scrape(
                args.url,
                category_id=args.category_id or 0,
                brand_id=args.brand_id,
                slug=args.slug,
                persist=persist,
            )
            _print_product(result)
            return 0

        if args.command == "run":
            processed = 0
            endpoints = repository.pending_endpoints(brand_slug=args.slug, limit=args.limit)
            for endpoint in endpoints:
                try:
                    result = scraper.process_endpoint(endpoint)
                    stored_id = result.stored.id if result.stored else "-"
                    print(f"{stored_id}\t{result.product.url}\t{result.product.title}")
                    processed += 1
                except ScraperError as exc:
                    print(f"error\t{endpoint.url}\t{exc}", file=sys.stderr)
            print(f"processed={processed}/{len(endpoints)}")
            return 0
    except ScraperError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 1
