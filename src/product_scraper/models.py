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
