"""Bulk-load a generated Dataset into an EMPTY schema using COPY."""
import psycopg

from data.generate import Dataset

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {  # insertion order respects foreign keys
    "customers": ("id", "full_name", "email", "region", "signup_date", "signup_channel"),
    "products": ("id", "name", "category", "supplier", "unit_price"),
    "orders": ("id", "customer_id", "order_date", "channel", "region", "status"),
    "order_items": ("id", "order_id", "product_id", "quantity", "unit_price"),
    "refunds": ("id", "order_item_id", "refund_date", "reason", "amount"),
}


def load_dataset(conn: psycopg.Connection, ds: Dataset) -> dict[str, int]:
    counts: dict[str, int] = {}
    with conn.transaction():  # all-or-nothing
        for table, columns in TABLE_COLUMNS.items():
            rows = getattr(ds, table)
            statement = f"COPY {table} ({', '.join(columns)}) FROM STDIN"
            with conn.cursor() as cur, cur.copy(statement) as copy:
                for row in rows:
                    copy.write_row(row)
            counts[table] = len(rows)
    return counts
