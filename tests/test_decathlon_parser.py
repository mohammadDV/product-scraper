from __future__ import annotations

import pytest

from product_scraper.exceptions import ParseError
from product_scraper.sites.decathlon import (
    DecathlonParser,
    parse_discount_text,
    parse_price_text,
    stock_from_status,
)
from tests.conftest import fixture_text

PRODUCT_URL = "https://www.decathlon.com.tr/p/mont/_/R-p-111?mc=8883162"
WRISTBAND_URL = "https://www.decathlon.com.tr/p/bileklik-sag-veya-sol-seviye-1/_/R-p-364504?mc=8941380"


@pytest.fixture
def parser() -> DecathlonParser:
    return DecathlonParser()


def test_parse_multi_size_product(parser: DecathlonParser) -> None:
    product = parser.parse_product(fixture_text("decathlon", "multi_size.html"), PRODUCT_URL)

    assert product.title == "Erkek Sıcak Tutan ve Su Geçirmez Yelkenli Montu - Lacivert - 100"
    assert product.code == "8883162"
    assert product.price == 1390
    assert product.discount == 22
    assert product.sizes == {"XS": "inStock", "S": "low", "Ş": "outOfStock"}
    assert product.related_product_ids == ("8827917", "8883162", "123")
    assert product.images == (
        "https://contents.mediadecathlon.com/p2887710/k$abc/sq/mont.jpg?format=auto&f=800x0",
        "https://contents.mediadecathlon.com/p2887711/k$def/sq/mont-back.jpg?format=auto&f=800x0",
    )
    assert product.related_urls() == [
        "https://www.decathlon.com.tr/p/mont/_/R-p-111?mc=8827917",
    ]


def test_parse_dropdown_sizes(parser: DecathlonParser) -> None:
    url = "https://www.decathlon.com.tr/p/erkek-outdoor-ayakkabi-gri-mh500/_/R-p-361186?mc=8928611"
    product = parser.parse_product(fixture_text("decathlon", "dropdown_sizes.html"), url)

    assert product.title == "Erkek Outdoor Ayakkabı - Gri - MH500"
    assert product.code == "8928611"
    assert product.price == 3850
    assert product.sizes == {"40": "inStock", "41": "inStock", "44": "low", "45": "outOfStock"}
    assert product.related_urls() == [
        "https://www.decathlon.com.tr/p/erkek-outdoor-ayakkabi-gri-mh500/_/R-p-361186?mc=8928608",
    ]


def test_parse_one_size_product(parser: DecathlonParser) -> None:
    product = parser.parse_product(fixture_text("decathlon", "one_size.html"), WRISTBAND_URL)

    assert product.title == "Bileklik Sağ veya Sol - Seviye 1"
    assert product.code == "8941380"
    assert product.price == 199
    assert product.discount == 0
    assert product.sizes == {"M 56-59cm": "inStock"}
    assert product.related_urls() == [
        "https://www.decathlon.com.tr/p/bileklik-sag-veya-sol-seviye-1/_/R-p-364504?mc=8941381",
    ]


def test_discount_ignores_recommended_carousel_products(parser: DecathlonParser) -> None:
    product = parser.parse_product(fixture_text("decathlon", "one_size.html"), WRISTBAND_URL)

    assert product.discount == 0
    assert product.price == 199


def test_discount_uses_main_product_not_recommendations(parser: DecathlonParser) -> None:
    url = "https://www.decathlon.com.tr/p/erkek-kapusonlu-fermuarli-sweatshirt-siyah/_/R-p-332651?mc=8773583"
    product = parser.parse_product(
        fixture_text("decathlon", "main_discount_with_recommendations.html"),
        url,
    )

    assert product.title == "Erkek Kapüşonlu Fermuarlı Sweatshirt - Siyah"
    assert product.code == "8773583"
    assert product.price == 750
    assert product.discount == 21


def test_parse_product_list(parser: DecathlonParser) -> None:
    links = parser.parse_product_list(
        fixture_text("decathlon", "product_list.html"),
        "https://www.decathlon.com.tr",
    )
    assert links == [
        "https://www.decathlon.com.tr/p/kadin-binici-yelegi-siyah-100/_/R-p-177631?mc=8404044",
        "https://www.decathlon.com.tr/p/bileklik-sag-veya-sol-seviye-1/_/R-p-364504?mc=8941380",
    ]


def test_missing_title_raises(parser: DecathlonParser) -> None:
    with pytest.raises(ParseError):
        parser.parse_product("<html><body><p>no product</p></body></html>", PRODUCT_URL)


def test_code_falls_back_to_mc_query(parser: DecathlonParser) -> None:
    html = "<html><body><h1>Test</h1></body></html>"
    product = parser.parse_product(html, WRISTBAND_URL)
    assert product.code == "8941380"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("&#8378;1.390", 1390),
        ("₺199,90", 199),
        ("1.390 TL", 1390),
        ("", 0),
    ],
)
def test_parse_price_text(raw: str, expected: int) -> None:
    assert parse_price_text(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("-22%", 22),
        ("22%", 22),
        ("", 0),
    ],
)
def test_parse_discount_text(raw: str, expected: int) -> None:
    assert parse_discount_text(raw) == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("inStock", 10),
        ("low", 5),
        ("outOfStock", 0),
        ("unknown", 10),
    ],
)
def test_stock_from_status(status: str, expected: int) -> None:
    assert stock_from_status(status, 10) == expected


def test_matches_decathlon_domains(parser: DecathlonParser) -> None:
    assert parser.matches(WRISTBAND_URL)
    assert parser.matches("https://www.decathlon.fr/p/foo")
    assert not parser.matches("https://www.adidas.com.tr/p/foo")
