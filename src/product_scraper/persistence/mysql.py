from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pymysql
from pymysql.cursors import DictCursor

from product_scraper.config import Settings
from product_scraper.exceptions import PersistenceError
from product_scraper.models import BrandRecord, EndpointRecord, ExistingProduct
from product_scraper.persistence.repository import ProductRepository


class MySQLProductRepository(ProductRepository):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @contextmanager
    def _connect(self) -> Iterator[pymysql.connections.Connection]:
        try:
            connection = pymysql.connect(
                host=self._settings.db_host,
                port=self._settings.db_port,
                user=self._settings.db_user,
                password=self._settings.db_password,
                database=self._settings.db_name,
                charset="utf8mb4",
                cursorclass=DictCursor,
                autocommit=False,
            )
        except pymysql.Error as exc:
            raise PersistenceError("Could not connect to the database") from exc
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_brand_by_slug(self, slug: str) -> BrandRecord | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, slug, domain FROM brands WHERE slug = %s LIMIT 1",
                    (slug,),
                )
                row = cursor.fetchone()
        return self._brand(row)

    def get_brand_by_id(self, brand_id: int) -> BrandRecord | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, slug, domain FROM brands WHERE id = %s LIMIT 1",
                    (brand_id,),
                )
                row = cursor.fetchone()
        return self._brand(row)

    def find_product_id_by_url(self, url: str) -> int | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM products WHERE url = %s LIMIT 1", (url,))
                row = cursor.fetchone()
        return int(row["id"]) if row else None

    def find_product_by_code(self, code: str, *, brand_id: int | None = None) -> ExistingProduct | None:
        sql = "SELECT id, url, code, brand_id FROM products WHERE code = %s"
        params: list = [code]
        if brand_id is not None:
            sql += " AND brand_id = %s"
            params.append(brand_id)
        sql += " LIMIT 1"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
        if not row:
            return None
        return ExistingProduct(
            id=int(row["id"]),
            url=row["url"] or "",
            code=str(row["code"] or ""),
            brand_id=int(row["brand_id"]),
        )

    def insert_product(self, fields: dict) -> int:
        columns = list(fields)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO products ({', '.join(columns)}) VALUES ({placeholders})"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, [fields[column] for column in columns])
                return int(cursor.lastrowid)

    def update_product(self, product_id: int, fields: dict) -> None:
        assignments = ", ".join(f"{column} = %s" for column in fields)
        sql = f"UPDATE products SET {assignments} WHERE id = %s"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, [*fields.values(), product_id])

    def sync_category(self, product_id: int, category_id: int) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM category_product WHERE product_id = %s AND category_id <> %s",
                    (product_id, category_id),
                )
                cursor.execute(
                    """
                    INSERT INTO category_product (product_id, category_id, created_at, updated_at)
                    VALUES (%s, %s, NOW(), NOW())
                    ON DUPLICATE KEY UPDATE updated_at = NOW()
                    """,
                    (product_id, category_id),
                )

    def upsert_image(
        self,
        product_id: int,
        path: str,
        file_type: str,
        status: int,
        priority: int,
    ) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id FROM files
                    WHERE product_id = %s AND path = %s AND type = %s
                    LIMIT 1
                    """,
                    (product_id, path, file_type),
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute(
                        "UPDATE files SET status = %s, priority = %s, updated_at = NOW() WHERE id = %s",
                        (status, priority, row["id"]),
                    )
                    return
                cursor.execute(
                    """
                    INSERT INTO files (product_id, path, type, status, priority, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                    """,
                    (product_id, path, file_type, status, priority),
                )

    def upsert_size(
        self,
        product_id: int,
        code: str,
        title: str,
        status: int,
        stock: int,
        priority: int,
    ) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM sizes WHERE product_id = %s AND code = %s LIMIT 1",
                    (product_id, code),
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute(
                        """
                        UPDATE sizes
                        SET title = %s, status = %s, stock = %s, priority = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (title, status, stock, priority, row["id"]),
                    )
                    return
                cursor.execute(
                    """
                    INSERT INTO sizes (title, code, stock, status, priority, product_id, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                    """,
                    (title, code, stock, status, priority, product_id),
                )

    def insert_endpoints_if_missing(self, rows: list[dict]) -> None:
        if not rows:
            return
        urls = [row["url"] for row in rows]
        placeholders = ", ".join(["%s"] * len(urls))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT url FROM endpoints WHERE url IN ({placeholders})",
                    urls,
                )
                existing = {row["url"] for row in cursor.fetchall()}
                new_rows = [row for row in rows if row["url"] not in existing]
                if not new_rows:
                    return
                cursor.executemany(
                    """
                    INSERT INTO endpoints (url, status, brand_id, category_id, created_at, updated_at)
                    VALUES (%(url)s, %(status)s, %(brand_id)s, %(category_id)s, NOW(), NOW())
                    """,
                    new_rows,
                )

    def pending_endpoints(self, *, brand_slug: str | None, limit: int) -> list[EndpointRecord]:
        sql = """
            SELECT e.id, e.url, e.brand_id, e.category_id, b.slug AS brand_slug, b.domain AS brand_domain
            FROM endpoints e
            INNER JOIN brands b ON b.id = e.brand_id
            WHERE e.status = 0 AND e.url IS NOT NULL
        """
        params: list = []
        if brand_slug:
            sql += " AND b.slug = %s"
            params.append(brand_slug)
        sql += " ORDER BY e.id ASC LIMIT %s"
        params.append(limit)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
        return [
            EndpointRecord(
                id=int(row["id"]),
                url=row["url"],
                brand_id=int(row["brand_id"]),
                category_id=int(row["category_id"]),
                brand_slug=row["brand_slug"],
                brand_domain=row["brand_domain"] or "",
            )
            for row in rows
        ]

    def mark_endpoint_done(self, endpoint_id: int) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE endpoints SET status = 1, updated_at = NOW() WHERE id = %s",
                    (endpoint_id,),
                )

    def _brand(self, row: dict | None) -> BrandRecord | None:
        if not row:
            return None
        return BrandRecord(id=int(row["id"]), slug=row["slug"], domain=row["domain"] or "")
