from __future__ import annotations

from dataclasses import asdict

from product_scraper.models import CatalogProduct, FieldChange, PreviewResult, ScrapedProduct
from product_scraper.sites.decathlon import stock_from_status

_REFRESH_FIELDS = ("price", "discount", "sizes")
_FULL_FIELDS = ("title", "code", "price", "discount", "images", "sizes")


def incoming_sizes(product: ScrapedProduct, default_stock: int) -> dict[str, int]:
    return {
        title.strip("."): stock_from_status(status, default_stock)
        for title, status in product.sizes.items()
    }


def diff_fields(
    product: ScrapedProduct,
    existing: CatalogProduct | None,
    *,
    action: str,
    default_stock: int,
) -> tuple[FieldChange, ...]:
    incoming = {
        "title": product.title,
        "code": product.code,
        "price": product.price,
        "discount": product.discount,
        "images": list(product.images),
        "sizes": incoming_sizes(product, default_stock),
    }
    if existing is None:
        current: dict[str, object] = {field: None for field in incoming}
    else:
        current = {
            "title": existing.title,
            "code": existing.code,
            "price": existing.price,
            "discount": existing.discount,
            "images": list(existing.images),
            "sizes": dict(existing.sizes),
        }

    fields = _REFRESH_FIELDS if action == "refresh" else _FULL_FIELDS
    return tuple(
        FieldChange(
            field=field,
            current=current[field],
            incoming=incoming[field],
            changed=current[field] != incoming[field],
        )
        for field in fields
    )


def preview_payload(result: PreviewResult) -> dict:
    payload = {
        "mode": result.mode,
        "action": result.action,
        "has_changes": result.has_changes,
        "product": asdict(result.product),
        "existing": asdict(result.existing) if result.existing else None,
        "changes": [asdict(change) for change in result.changes],
    }
    if result.stored is not None:
        payload["stored"] = asdict(result.stored)
    return payload
