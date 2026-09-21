from __future__ import annotations

import html as html_lib
import re
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from product_scraper.exceptions import ParseError
from product_scraper.models import ScrapedProduct
from product_scraper.sites.base import SiteParser

_CODE_RE = re.compile(r"Ref\.\s*:\s*(\d+)", re.IGNORECASE)
_DISCOUNT_RE = re.compile(r"(-?\d+)\s*%")
_CURRENCY_RE = re.compile(r"[₺€$£¥]|TL", re.IGNORECASE)
_NON_DIGIT_RE = re.compile(r"[^\d]")
_SIZE_CLASS_RE = re.compile(r"\b(inStock|low|outOfStock)\b", re.IGNORECASE)
_RECOMMENDED_CLASSES = frozenset({"product-block", "product-carousel-item"})


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = html_lib.unescape(value)
    return re.sub(r"\s+", " ", text).strip()


def _unique(items: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return tuple(result)


class DecathlonParser(SiteParser):
    slug = "decathlon"

    def matches(self, url: str) -> bool:
        host = urlsplit(url).hostname or ""
        return "decathlon." in host.lower()

    def parse_product(self, html: str, url: str) -> ScrapedProduct:
        soup = _soup(html)
        title = self._extract_title(soup)
        if not title:
            raise ParseError(f"Product title not found for {url}")

        sizes = self._extract_sizes(soup)
        if not sizes:
            sizes = self._extract_one_size(soup)

        return ScrapedProduct(
            url=url,
            title=title,
            code=self._extract_code(soup, url),
            price=self._extract_price(soup),
            discount=self._extract_discount(soup),
            images=self._extract_images(soup),
            sizes=sizes,
            related_product_ids=self._extract_related_ids(soup),
        )

    def parse_product_list(self, html: str, domain: str) -> list[str]:
        soup = _soup(html)
        links: list[str] = []
        for anchor in soup.select(".dpb-bottom-btn-padding > a[href], a.dpb-product-model-link[href]"):
            href = self._extract_list_href(anchor.get("href"))
            if href:
                links.append(urljoin(domain.rstrip("/") + "/", href.lstrip("/")))
        return list(_unique(links))

    def _extract_title(self, soup: BeautifulSoup) -> str:
        heading = soup.find("h1")
        if heading is None:
            return ""
        return _clean_text(heading.get_text(" ", strip=True))

    def _extract_code(self, soup: BeautifulSoup, url: str) -> str:
        node = soup.select_one(".current-selected-model")
        if node is not None:
            match = _CODE_RE.search(_clean_text(node.get_text(" ", strip=True)))
            if match:
                return match.group(1)
        query = urlsplit(url).query
        for part in query.split("&"):
            if part.startswith("mc="):
                return part.split("=", 1)[1]
        return ""

    def _extract_price(self, soup: BeautifulSoup) -> int:
        node = self._first_main_node(
            soup,
            (
                ".vtmn-items-end > span.vtmn-price",
                ".vtmn-items-end > span",
                "span.vtmn-price_size--large",
                "span.vtmn-price",
            ),
        )
        if node is None:
            return 0
        return parse_price_text(node.get_text(" ", strip=True))

    def _extract_discount(self, soup: BeautifulSoup) -> int:
        node = self._first_main_node(soup, (".price-discount-rate", ".price-discount"))
        if node is None:
            return 0
        return parse_discount_text(node.get_text(" ", strip=True))

    def _main_product_root(self, soup: BeautifulSoup) -> Tag:
        root = soup.select_one("article.product-main-infos--grid")
        if root is not None:
            return root
        heading = soup.find("h1")
        if isinstance(heading, Tag):
            article = heading.find_parent("article")
            if article is not None:
                return article
            section = heading.find_parent("section")
            if section is not None:
                return section
        return soup

    def _first_main_node(self, soup: BeautifulSoup, selectors: tuple[str, ...]) -> Tag | None:
        root = self._main_product_root(soup)
        for selector in selectors:
            for node in root.select(selector):
                if not _is_recommended(node):
                    return node
        return None

    def _extract_sizes(self, soup: BeautifulSoup) -> dict[str, str]:
        sizes: dict[str, str] = {}
        for button in soup.select(".vtmn-sku-selector__grid > button"):
            size_node = button.select_one(".vtmn-sku-selector__grid-item-size")
            if size_node is None:
                continue
            size = _clean_text(size_node.get_text(" ", strip=True)).strip(".")
            if not size:
                continue
            sizes[size] = self._stock_status(button)

        if sizes:
            return sizes

        for item in soup.select("li.vtmn-sku-selector__item, .vtmn-sku-selector__items [role=option]"):
            size = self._direct_text(item).strip(".")
            if not size:
                continue
            sizes[size] = self._stock_status(item)
        return sizes

    def _extract_one_size(self, soup: BeautifulSoup) -> dict[str, str]:
        node = soup.select_one(".vtmn-sku-selector--monosku")
        if node is None:
            return {}
        size = self._direct_text(node).strip(".")
        if not size:
            return {}
        return {size: self._stock_status(node)}

    def _direct_text(self, node: Tag) -> str:
        parts: list[str] = []
        for child in node.children:
            if isinstance(child, Tag) and child.name in {"span", "div"}:
                break
            parts.append(child if isinstance(child, str) else child.get_text(" ", strip=True))
        return _clean_text("".join(parts))

    def _stock_status(self, node: Tag) -> str:
        class_attr = " ".join(node.get("class", []))
        match = _SIZE_CLASS_RE.search(class_attr)
        if match:
            return match.group(1)
        stock_node = node.select_one("[class*='sku-selector__stock--']")
        if stock_node is not None:
            match = _SIZE_CLASS_RE.search(" ".join(stock_node.get("class", [])))
            if match:
                return match.group(1)
        return "unknown"

    def _extract_related_ids(self, soup: BeautifulSoup) -> tuple[str, ...]:
        ids: list[str] = []
        for button in soup.select(".variant-list__item > button[data-id], button.variant-list__button[data-id]"):
            data_id = str(button.get("data-id") or "").strip()
            if data_id.isdigit():
                ids.append(data_id)
        return _unique(ids)

    def _extract_images(self, soup: BeautifulSoup) -> tuple[str, ...]:
        urls: list[str] = []
        for img in soup.select("img.swiper-media__image, .swiper-media__image"):
            src = img.get("src") if isinstance(img, Tag) else None
            if src:
                urls.append(normalize_image_url(src))
        return _unique(urls)

    def _extract_list_href(self, href: str | list[str] | None) -> str:
        if isinstance(href, list):
            href = href[0] if href else ""
        if not href:
            return ""
        href = html_lib.unescape(href)
        href = href.split("&", 1)[0]
        parts = urlsplit(href)
        if parts.scheme or parts.netloc:
            return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query.split("&", 1)[0], ""))
        return href


def _is_recommended(node: Tag) -> bool:
    """True for carousel / 'more products' cards, not the PDP itself."""
    for parent in (node, *node.parents):
        classes = parent.get("class", [])
        if not isinstance(classes, list):
            classes = str(classes).split()
        if _RECOMMENDED_CLASSES.intersection(classes):
            return True
    return False


def parse_price_text(raw: str) -> int:
    if not raw:
        return 0
    price = html_lib.unescape(raw)
    price = _CURRENCY_RE.sub("", price)
    price = price.replace("\xa0", " ").strip()
    price = price.replace(".", "")
    if "," in price:
        price = price.split(",", 1)[0]
    digits = _NON_DIGIT_RE.sub("", price)
    return int(digits) if digits else 0


def parse_discount_text(raw: str) -> int:
    if not raw:
        return 0
    match = _DISCOUNT_RE.search(html_lib.unescape(raw))
    if not match:
        return 0
    return abs(int(match.group(1)))


def normalize_image_url(src: str) -> str:
    return html_lib.unescape(unquote(src)).strip()


def stock_from_status(status: str, default_stock: int) -> int:
    mapping = {
        "instock": default_stock,
        "low": 5,
        "outofstock": 0,
    }
    return mapping.get(status.lower(), default_stock)
