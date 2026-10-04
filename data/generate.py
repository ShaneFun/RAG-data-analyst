"""Synthetic data generator for Larkspur Market.

Pure Python, no database. Same seed -> identical output.
Planted trends (ground truth):
  T1 holiday spike: Nov/Dec order volume x1.8
  T2 bad supplier: Brightline Goods items refunded ~15% vs ~5%
  T3 March 2025 North drop: most North Electronics items vanish (stock-out)
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

# ---------- Shop settings ----------
REGIONS = ["North", "South", "East", "West"]
CATEGORY_PRICES = {                      # (min price, max price) per category
    "Electronics": (50.0, 800.0),
    "Home": (15.0, 300.0),
    "Fashion": (10.0, 200.0),
    "Beauty": (5.0, 80.0),
    "Sports": (15.0, 400.0),
    "Grocery": (2.0, 40.0),
}
CATEGORIES = list(CATEGORY_PRICES)
SUPPLIERS = [
    "Brightline Goods",
    "Copperleaf Trading",
    "Harbor & Pine Co",
    "Meridian Wholesale",
    "Oakridge Partners",
    "Silverstream Supply",
    "Tidewater Imports",
    "Willow Lane Makers",
]
BAD_SUPPLIER = "Brightline Goods"
FIRST_NAMES = ["Aoife", "Liam", "Siobhan", "Conor", "Mei", "Arjun", "Sofia", "Noah",
               "Niamh", "Ethan", "Aisha", "Lucas", "Chloe", "Ravi", "Emma", "Jack"]
LAST_NAMES = ["Murphy", "Kelly", "Tan", "Byrne", "Lim", "Walsh", "Singh", "Ryan",
              "Chen", "O'Brien", "Lee", "Doyle", "Patel", "Nolan", "Wong", "Burke"]
REFUND_REASONS = ["damaged", "wrong item", "not as described", "changed mind", "late delivery"]

# ---------- Sizes and planted-trend strengths ----------
N_CUSTOMERS = 2000
PRODUCTS_PER_CATEGORY = 20
TARGET_ORDERS = 10_000
HOLIDAY_FACTOR = 1.8              # T1
CANCEL_RATE = 0.05
APP_SHARE = 0.4
BASE_REFUND_RATE = 0.05
BAD_SUPPLIER_REFUND_RATE = 0.15   # T2
STOCKOUT_DROP = 0.85              # T3: share of North Electronics items removed in March 2025


@dataclass
class Dataset:
    """All generated rows. Each row is a tuple in the same column order as the table."""
    customers: list[tuple] = field(default_factory=list)    # (id, full_name, email, region, signup_date, signup_channel)
    products: list[tuple] = field(default_factory=list)     # (id, name, category, supplier, unit_price)
    orders: list[tuple] = field(default_factory=list)       # (id, customer_id, order_date, channel, region, status)
    order_items: list[tuple] = field(default_factory=list)  # (id, order_id, product_id, quantity, unit_price)
    refunds: list[tuple] = field(default_factory=list)      # (id, order_item_id, refund_date, reason, amount)


def _months() -> list[tuple[int, int]]:
    return [(y, m) for y in (2024, 2025) for m in range(1, 13)]   # 24 months


def _month_days(year: int, month: int) -> int:
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days


def generate(seed: int = 42) -> Dataset:
    rng = random.Random(seed)       # our own random generator: same seed -> same "random" numbers
    ds = Dataset()

    # 1) Customers (all signed up during 2023, before any order). Emails use example.com (fake).
    for cid in range(1, N_CUSTOMERS + 1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        name = f"{first} {last}"
        email = f"{first}.{last}{cid}".lower().replace("'", "") + "@example.com"
        signup = date(2023, 1, 1) + timedelta(days=rng.randrange(365))
        ds.customers.append((cid, name, email, rng.choice(REGIONS), signup,
                             rng.choice(["web", "app"])))
    customer_region = {c[0]: c[3] for c in ds.customers}

    # 2) Products: 20 per category; suppliers assigned in turn so each has 15 products
    pid = 0
    for category in CATEGORIES:
        low, high = CATEGORY_PRICES[category]
        for n in range(1, PRODUCTS_PER_CATEGORY + 1):
            pid += 1
            supplier = SUPPLIERS[(pid - 1) % len(SUPPLIERS)]
            price = round(rng.uniform(low, high), 2)
            ds.products.append((pid, f"{category} Item {n:02d}", category, supplier, price))
    product_by_id = {p[0]: p for p in ds.products}
    product_ids = list(product_by_id)

    # 3) Orders: a fixed number per month, with Nov/Dec boosted (T1)
    months = _months()
    weights = [HOLIDAY_FACTOR if m in (11, 12) else 1.0 for _, m in months]
    base = TARGET_ORDERS / sum(weights)          # orders in a normal month

    order_id = item_id = refund_id = 0
    for (year, month), weight in zip(months, weights):
        for _ in range(round(base * weight)):
            order_date = date(year, month, 1) + timedelta(days=rng.randrange(_month_days(year, month)))
            customer_id = rng.randint(1, N_CUSTOMERS)
            region = customer_region[customer_id]          # order region = customer's region
            channel = "app" if rng.random() < APP_SHARE else "web"
            status = "cancelled" if rng.random() < CANCEL_RATE else "completed"

            # 4) Order lines (1-4 products per order)
            items = []
            for _ in range(rng.choice([1, 1, 2, 2, 3, 4])):
                product = product_by_id[rng.choice(product_ids)]
                quantity = rng.choice([1, 1, 1, 2, 2, 3])
                stockout = (region == "North" and (year, month) == (2025, 3)
                            and product[2] == "Electronics")
                if stockout and rng.random() < STOCKOUT_DROP:
                    continue  # T3: out of stock -> this item is never sold
                items.append((product, quantity))
            if not items:
                continue  # every item was out of stock -> the whole order is lost

            order_id += 1
            ds.orders.append((order_id, customer_id, order_date, channel, region, status))
            for product, quantity in items:
                item_id += 1
                ds.order_items.append((item_id, order_id, product[0], quantity, product[4]))

                # 5) Refunds: only for completed orders; Brightline refunded 3x more often (T2)
                if status != "completed":
                    continue
                rate = BAD_SUPPLIER_REFUND_RATE if product[3] == BAD_SUPPLIER else BASE_REFUND_RATE
                if rng.random() < rate:
                    refund_id += 1
                    ds.refunds.append((refund_id, item_id,
                                       order_date + timedelta(days=rng.randint(3, 30)),
                                       rng.choice(REFUND_REASONS),
                                       round(product[4] * quantity, 2)))
    return ds