from __future__ import annotations

from unittest.mock import MagicMock, patch

from product_scraper.config import Settings
from product_scraper.persistence.mysql import MySQLProductRepository
from product_scraper.persistence.storage import ProductStorage
from tests.fakes import InMemoryProductRepository
from tests.test_storage import URL, _product


def test_store_records_inventory_transactions(settings: Settings) -> None:
    repo = InMemoryProductRepository()
    storage = ProductStorage(repo, settings)

    stored = storage.store(_product(), category_id=4, brand_id=2)

    # outOfStock (0) from empty previous is a no-op — only positive initial stocks are logged
    assert len(repo.inventory_transactions) == 2
    size_ids = {item["code"]: int(item["id"]) for item in repo.sizes if item["product_id"] == stored.id}
    by_size = {row["size_id"]: row for row in repo.inventory_transactions}

    assert by_size[size_ids["M 56-59cm"]]["quantity_change"] == 10
    assert by_size[size_ids["M 56-59cm"]]["type"] == "adjust"
    assert by_size[size_ids["M 56-59cm"]]["source"] == "scraper"
    assert by_size[size_ids["L"]]["quantity_change"] == 5
    assert size_ids["XL"] not in by_size


def test_update_price_and_stock_records_delta_only(settings: Settings) -> None:
    repo = InMemoryProductRepository()
    storage = ProductStorage(repo, settings)
    stored = storage.store(_product(), category_id=4, brand_id=2)
    before = len(repo.inventory_transactions)

    storage.update_price_and_stock(
        _product(sizes={"M 56-59cm": "outOfStock", "L": "inStock"}),
        stored.id,
    )

    new_rows = repo.inventory_transactions[before:]
    # M: 10 -> 0, L: 5 -> 10, XL unchanged (not in payload so not upserted)
    assert {(row["previous_quantity"], row["resulting_quantity"], row["quantity_change"]) for row in new_rows} == {
        (10, 0, -10),
        (5, 10, 5),
    }
    assert all(row["type"] == "adjust" and row["source"] == "scraper" for row in new_rows)


def test_upsert_size_skips_ledger_when_quantity_unchanged(settings: Settings) -> None:
    repo = InMemoryProductRepository()
    storage = ProductStorage(repo, settings)
    stored = storage.store(_product(sizes={"M": "inStock"}), category_id=4, brand_id=2)
    before = len(repo.inventory_transactions)

    repo.upsert_size(stored.id, "M", "M", 1, 10, 1)

    assert len(repo.inventory_transactions) == before


def test_mysql_upsert_size_inserts_inventory_transaction(settings: Settings) -> None:
    repo = MySQLProductRepository(settings)
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        None,  # no existing size
        None,  # no existing stock
    ]
    cursor.lastrowid = 42

    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    connection.cursor.return_value.__exit__.return_value = False

    with patch.object(repo, "_connect") as connect:
        connect.return_value.__enter__.return_value = connection
        connect.return_value.__exit__.return_value = False
        repo.upsert_size(
            product_id=7,
            code="M",
            title="M",
            status=1,
            stock=10,
            priority=1,
        )

    executed = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("INSERT INTO inventory_transactions" in sql for sql in executed)
    insert_call = next(
        call for call in cursor.execute.call_args_list if "INSERT INTO inventory_transactions" in call.args[0]
    )
    assert insert_call.args[1] == (
        7,
        42,
        "adjust",
        "scraper",
        10,
        0,
        10,
        "scraper upsert_size",
    )


def test_mysql_upsert_size_skips_ledger_when_unchanged(settings: Settings) -> None:
    repo = MySQLProductRepository(settings)
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        {"id": 42},  # existing size
        {"id": 1, "quantity": 10},  # existing stock
    ]

    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    connection.cursor.return_value.__exit__.return_value = False

    with patch.object(repo, "_connect") as connect:
        connect.return_value.__enter__.return_value = connection
        connect.return_value.__exit__.return_value = False
        repo.upsert_size(
            product_id=7,
            code="M",
            title="M",
            status=1,
            stock=10,
            priority=1,
        )

    executed = [call.args[0] for call in cursor.execute.call_args_list]
    assert not any("INSERT INTO inventory_transactions" in sql for sql in executed)
