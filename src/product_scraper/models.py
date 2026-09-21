from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScrapedProduct:
    url: str
    title: str
    code: str
    price: int
    discount: int
    images: tuple[str, ...] = ()
    sizes: dict[str, str] = field(default_factory=dict)
    related_product_ids: tuple[str, ...] = ()

    def related_urls(self) -> list[str]:
        base = self.url.split("?", 1)[0]
        urls: list[str] = []
        seen: set[str] = set()
        for related_id in self.related_product_ids:
            if len(related_id) <= 5 or related_id == self.code:
                continue
            related_url = f"{base}?mc={related_id}"
            if related_url in seen:
                continue
            seen.add(related_url)
            urls.append(related_url)
        return urls


@dataclass(frozen=True)
class BrandRecord:
    id: int
    slug: str
    domain: str


@dataclass(frozen=True)
class EndpointRecord:
    id: int
    url: str
    brand_id: int
    category_id: int
    brand_slug: str
    brand_domain: str


@dataclass(frozen=True)
class StoredProduct:
    id: int
    url: str
    created: bool


@dataclass(frozen=True)
class ExistingProduct:
    """A product already stored in the catalog; used for offer-only refreshes."""

    id: int
    url: str
    code: str
    brand_id: int


@dataclass(frozen=True)
class CatalogProduct:
    """Snapshot of a stored product used for admin preview diffs."""

    id: int
    url: str
    title: str
    code: str
    price: int
    discount: int
    brand_id: int
    category_id: int | None = None
    images: tuple[str, ...] = ()
    sizes: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class FieldChange:
    field: str
    current: object
    incoming: object
    changed: bool


@dataclass(frozen=True)
class PreviewResult:
    mode: str
    action: str
    product: ScrapedProduct
    existing: CatalogProduct | None
    changes: tuple[FieldChange, ...] = ()
    stored: StoredProduct | None = None

    @property
    def has_changes(self) -> bool:
        return any(change.changed for change in self.changes)
