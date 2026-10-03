# Plan 1: Data, Knowledge Base and SQL Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and test the back-end foundation of the AI Data Analyst: a Postgres database filled with synthetic Larkspur Market data (3 planted trends), a read-only role that can't see personal data, a pgvector knowledge base with semantic search, and a SQL safety layer (validator + executor) that only runs safe, limited, read-only SELECTs.

**Architecture:** Local Postgres 16 + pgvector runs in Docker. Pure-Python data generator → COPY loader → roles/views. Knowledge YAML → FastEmbed (`BAAI/bge-small-en-v1.5`, 384-d) → `knowledge` table → cosine search. The `sqlglot` validator checks every query before a pooled read-only connection executes it inside a read-only transaction with a statement timeout. Milestones 1–3 of the spec; later plans add the agent, API, front end, evaluation and deployment.

**Tech Stack:** Python 3.12, uv, psycopg 3 + psycopg_pool, pgvector, fastembed, sqlglot, pydantic-settings, PyYAML, pytest, ruff, Docker (`pgvector/pgvector:pg16`).

**Spec:** `docs/superpowers/specs/2026-10-03-ai-data-analyst-design.md`

## Global Constraints
- Python **3.12** (`requires-python = ">=3.12,<3.13"`); dependencies managed with **uv**; back-end code lives in `backend/`, setup scripts and data in `data/`.
- Generator seed **42**; ~2,000 customers, 120 products (20 × 6 categories), 8 suppliers, 4 regions, ~10,000 orders dated 2024-01-01 to 2025-12-31.
- Planted trends (must hold): **T1** avg Nov–Dec monthly orders ≥ 1.5 × avg of other months; **T2** `Brightline Goods` refund rate ≥ 2.5 × the average of the other suppliers; **T3** North Electronics orders in Mar 2025 ≤ 40% of the Feb/Apr 2025 mean, while all other regions combined stay ≥ 80% of theirs.
- Personal data (`full_name`, `email`) only in `customers`; role `analyst_ro` can read only `customers_safe`, `products`, `orders`, `order_items`, `refunds`; `statement_timeout = 5s`.
- Knowledge: kinds `dictionary` (5), `glossary` (9), `example` (15); embeddings are 384-d; search returns the top **5** by cosine similarity.
- Every executed query passes the validator; results are capped at **200** rows.
- No real customer data anywhere; fake emails use the reserved domain `example.com`.

## Prerequisites (the human does these once, before Task 1)
1. Install **Docker Desktop for Windows** (docker.com/products/docker-desktop), start it, and confirm `docker --version` and `docker compose version` work in a new terminal.
2. Install **uv**: `python -m pip install --user uv`, then confirm `uv --version` (open a new terminal if it isn't found).
3. All commands below are run from the repo root `C:\Users\siangyou\Projects\ai-data-analyst` unless a step says `cd backend`.

## Review Focus
1. **SQL that tries to escape the guard rails** (e.g. `SELECT set_config('statement_timeout','0',false)`, `pg_sleep`, `SELECT … INTO`, `FOR UPDATE`) must be rejected before it reaches the database, and a pooled connection must never keep changed session settings. Tests: Task 7 (validator cases), Task 8 (pool reset test).
2. **Attempts to read personal data or system catalogs** (`customers`, `pg_catalog.*`, `information_schema.*`, subqueries on `customers`) must fail at both layers. Tests: Task 4 (database permissions), Task 7 (validator).
3. **Huge result sets** (`SELECT * FROM order_items`, `LIMIT 5000`) must come back capped at 200 rows, never thousands. Tests: Task 7 (LIMIT rewriting), Task 8 (row cap).
4. **Expensive queries** (a cross join) must time out with a helpful message, and the next query on the pool must still work. Test: Task 8.
5. **Blank or whitespace input** to the validator or to knowledge search must give a clean rejection or an empty result, not a crash. Tests: Task 6, Task 7.

---

## File Structure

| File | Responsibility |
|---|---|
| `docker-compose.yml` | Local Postgres 16 + pgvector (the API service is added in a later plan) |
| `.gitignore`, `.env.example` | Ignore rules; documented environment variables |
| `backend/pyproject.toml` | Dependencies, pytest and ruff config; `app` package |
| `backend/app/config.py` | `Settings` (database URLs, read-only password, embedding model, timeout, row cap) |
| `backend/app/db.py` | `make_pool()`: psycopg connection pool that resets session state |
| `backend/app/knowledge/embed.py` | `Embedder`: FastEmbed wrapper (passages vs. queries) |
| `backend/app/knowledge/search.py` | `search_knowledge()` → `KnowledgeHit` list |
| `backend/app/sql/validator.py` | `validate_sql()` → `ValidationResult` |
| `backend/app/sql/executor.py` | `run_select()` → `SqlResult` |
| `data/schema.sql` | Tables, indexes, `vector` extension, `knowledge` table |
| `data/db_setup.py` | `reset_schema()`, `apply_schema()` |
| `data/generate.py` | `generate(seed)` → `Dataset` (pure Python, trends planted) |
| `data/load_data.py` | `load_dataset()`: COPY a `Dataset` into Postgres |
| `data/roles.py` | `setup_roles()`: `customers_safe` view + `analyst_ro` role + grants |
| `data/knowledge/*.yaml` | Dictionary, glossary, example question→SQL sources |
| `data/knowledge_entries.py` | `KnowledgeEntry`, `load_entries()`, `load_examples()` |
| `data/load_knowledge.py` | `entry_text()`, `load_knowledge()`: embed + insert |
| `data/setup_db.py` | One command that builds the whole dev database |
| `backend/tests/conftest.py` | Test databases and shared fixtures |
| `backend/tests/test_*.py` | One test file per unit |
| `DECISIONS.md`, `NOTES.md` | Interview script and session notes |

---

### Task 1: Project scaffold, local Postgres and test harness

**Files:**
- Create: `.gitignore`, `.env.example`, `docker-compose.yml`, `data/__init__.py`
- Create: `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/config.py`
- Create: `backend/tests/helpers.py`, `backend/tests/conftest.py`, `backend/tests/test_smoke.py`

**Interfaces:**
- Produces: `app.config.Settings`, `app.config.get_settings() -> Settings`; test helper `tests.helpers.ensure_database(name: str) -> str` (returns an admin connection URL for that database).

- [ ] **Step 1: Create the repo files**

`.gitignore`:
```gitignore
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
node_modules/
.next/
```

`.env.example`:
```dotenv
# Admin connection (setup scripts, knowledge search). Never given to the LLM.
DATABASE_URL_ADMIN=postgresql://postgres:postgres@localhost:5432/larkspur
# Read-only connection used to run agent SQL.
DATABASE_URL_RO=postgresql://analyst_ro:analyst_ro@localhost:5432/larkspur
ANALYST_RO_PASSWORD=analyst_ro
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
SQL_TIMEOUT=5s
MAX_ROWS=200
```

`docker-compose.yml`:
```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: larkspur
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d larkspur"]
      interval: 2s
      timeout: 3s
      retries: 30

volumes:
  pgdata:
```

`data/__init__.py`: empty file.
`backend/app/__init__.py`: empty file.

- [ ] **Step 2: Create `backend/pyproject.toml`**

```toml
[project]
name = "larkspur-analyst"
version = "0.1.0"
description = "AI Data Analyst agent for the Larkspur Market demo shop"
requires-python = ">=3.12,<3.13"
dependencies = [
    "psycopg[binary]>=3.3,<4",
    "psycopg-pool>=3.3,<4",
    "pgvector>=0.5,<0.6",
    "fastembed>=0.8,<0.9",
    "sqlglot>=30.21,<31",
    "pydantic-settings>=2.15,<3",
    "pyyaml>=6,<7",
    "numpy>=2,<3",
]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.pytest.ini_options]
pythonpath = ["..", "."]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```
`pythonpath = ["..", "."]` puts the repo root (for `import data.…`) and `backend/` (for `import tests.helpers`) on the import path; `app` is installed into the venv by uv.

- [ ] **Step 3: Write the failing tests**

`backend/tests/helpers.py`:
```python
import os

import psycopg
from psycopg import sql

ADMIN_BASE = os.environ.get("TEST_PG_ADMIN", "postgresql://postgres:postgres@localhost:5432")


def ensure_database(name: str) -> str:
    """Create the database if missing and return an admin URL for it."""
    with psycopg.connect(f"{ADMIN_BASE}/postgres", autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return f"{ADMIN_BASE}/{name}"
```

`backend/tests/conftest.py`:
```python
"""Shared pytest fixtures. Later tasks append fixtures below."""
```

`backend/tests/test_smoke.py`:
```python
import psycopg

from app.config import Settings
from tests.helpers import ensure_database


def test_settings_have_local_defaults():
    s = Settings(_env_file=None)
    assert s.database_url_admin.startswith("postgresql://postgres:")
    assert s.database_url_ro.startswith("postgresql://analyst_ro:")
    assert s.embedding_model == "BAAI/bge-small-en-v1.5"
    assert s.sql_timeout == "5s"
    assert s.max_rows == 200


def test_can_connect_to_test_database():
    url = ensure_database("larkspur_test")
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT 1").fetchone() == (1,)
```

- [ ] **Step 4: Start Postgres, install deps, and run the tests to see them fail**

Run:
```bash
docker compose up -d --wait
cd backend
uv python install 3.12
uv python pin 3.12
uv sync
uv run pytest -v
```
Expected: `test_settings_have_local_defaults` FAILS with `ModuleNotFoundError: No module named 'app.config'`. (`test_can_connect_to_test_database` may also fail at import time; that's expected.)

- [ ] **Step 5: Implement `backend/app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url_admin: str = "postgresql://postgres:postgres@localhost:5432/larkspur"
    database_url_ro: str = "postgresql://analyst_ro:analyst_ro@localhost:5432/larkspur"
    analyst_ro_password: str = "analyst_ro"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    sql_timeout: str = "5s"
    max_rows: int = 200


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: Run the tests to see them pass**

Run (in `backend/`): `uv run pytest -v`
Expected: 2 passed.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check .
cd ..
git add .gitignore .env.example docker-compose.yml data/__init__.py backend/pyproject.toml backend/uv.lock backend/.python-version backend/app backend/tests
git commit -m "chore: scaffold backend, local Postgres and test harness"
```

---

### Task 2: Database schema and indexes

**Files:**
- Create: `data/schema.sql`, `data/db_setup.py`
- Test: `backend/tests/test_schema.py`

**Interfaces:**
- Consumes: `ensure_database(name) -> str` (Task 1).
- Produces: `data.db_setup.reset_schema(conn: psycopg.Connection) -> None`, `data.db_setup.apply_schema(conn: psycopg.Connection) -> None`; tables `customers, products, orders, order_items, refunds, knowledge`.

- [ ] **Step 1: Write the failing test** (`backend/tests/test_schema.py`)

```python
import psycopg
import pytest

from data.db_setup import apply_schema, reset_schema
from tests.helpers import ensure_database

EXPECTED_TABLES = {"customers", "products", "orders", "order_items", "refunds", "knowledge"}
EXPECTED_INDEXES = {
    "idx_orders_order_date", "idx_orders_region", "idx_orders_customer_id",
    "idx_order_items_order_id", "idx_order_items_product_id",
    "idx_products_category", "idx_products_supplier",
}


@pytest.fixture
def schema_conn():
    url = ensure_database("larkspur_test_schema")
    with psycopg.connect(url, autocommit=True) as conn:
        reset_schema(conn)
        apply_schema(conn)
        yield conn


def test_all_tables_exist(schema_conn):
    rows = schema_conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    ).fetchall()
    assert EXPECTED_TABLES <= {r[0] for r in rows}


def test_indexes_exist(schema_conn):
    rows = schema_conn.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
    ).fetchall()
    assert EXPECTED_INDEXES <= {r[0] for r in rows}


def test_knowledge_embedding_is_384_dim_vector(schema_conn):
    row = schema_conn.execute(
        "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
        "WHERE attrelid = 'knowledge'::regclass AND attname = 'embedding'"
    ).fetchone()
    assert row == ("vector(384)",)


def test_apply_schema_is_repeatable(schema_conn):
    reset_schema(schema_conn)
    apply_schema(schema_conn)  # must not raise on a second build
```

- [ ] **Step 2: Run the test to see it fail**

Run (in `backend/`): `uv run pytest tests/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data.db_setup'`.

- [ ] **Step 3: Create `data/schema.sql`**

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE customers (
    id             integer PRIMARY KEY,
    full_name      text    NOT NULL,
    email          text    NOT NULL UNIQUE,
    region         text    NOT NULL,
    signup_date    date    NOT NULL,
    signup_channel text    NOT NULL CHECK (signup_channel IN ('web', 'app'))
);

CREATE TABLE products (
    id         integer       PRIMARY KEY,
    name       text          NOT NULL,
    category   text          NOT NULL,
    supplier   text          NOT NULL,
    unit_price numeric(10,2) NOT NULL
);

CREATE TABLE orders (
    id          integer PRIMARY KEY,
    customer_id integer NOT NULL REFERENCES customers(id),
    order_date  date    NOT NULL,
    channel     text    NOT NULL CHECK (channel IN ('web', 'app')),
    region      text    NOT NULL,
    status      text    NOT NULL CHECK (status IN ('completed', 'cancelled'))
);

CREATE TABLE order_items (
    id         integer       PRIMARY KEY,
    order_id   integer       NOT NULL REFERENCES orders(id),
    product_id integer       NOT NULL REFERENCES products(id),
    quantity   integer       NOT NULL CHECK (quantity > 0),
    unit_price numeric(10,2) NOT NULL
);

CREATE TABLE refunds (
    id            integer       PRIMARY KEY,
    order_item_id integer       NOT NULL UNIQUE REFERENCES order_items(id),
    refund_date   date          NOT NULL,
    reason        text          NOT NULL,
    amount        numeric(10,2) NOT NULL
);

CREATE TABLE knowledge (
    id        serial PRIMARY KEY,
    kind      text   NOT NULL CHECK (kind IN ('dictionary', 'glossary', 'example')),
    title     text   NOT NULL,
    content   text   NOT NULL,
    embedding vector(384) NOT NULL
);

CREATE INDEX idx_orders_order_date       ON orders (order_date);
CREATE INDEX idx_orders_region           ON orders (region);
CREATE INDEX idx_orders_customer_id      ON orders (customer_id);
CREATE INDEX idx_order_items_order_id    ON order_items (order_id);
CREATE INDEX idx_order_items_product_id  ON order_items (product_id);
CREATE INDEX idx_products_category       ON products (category);
CREATE INDEX idx_products_supplier       ON products (supplier);
-- refunds.order_item_id is already indexed by its UNIQUE constraint.
```

- [ ] **Step 4: Create `data/db_setup.py`**

```python
"""Build the database schema. reset_schema() DELETES everything in schema public."""
from pathlib import Path

import psycopg

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def reset_schema(conn: psycopg.Connection) -> None:
    conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
    conn.execute("CREATE SCHEMA public")


def apply_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
```

- [ ] **Step 5: Run the tests to see them pass**

Run (in `backend/`): `uv run pytest tests/test_schema.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
cd ..
git add data/schema.sql data/db_setup.py backend/tests/test_schema.py
git commit -m "feat(data): schema with indexes and knowledge vector table"
```

---

### Task 3: Synthetic data generator with planted trends

**Files:**
- Create: `data/generate.py`
- Modify: `backend/tests/conftest.py` (add the `dataset` fixture)
- Test: `backend/tests/test_generate.py`

**Interfaces:**
- Produces: `data.generate.generate(seed: int = 42) -> Dataset`; `Dataset` with list-of-tuple fields `customers (id, full_name, email, region, signup_date, signup_channel)`, `products (id, name, category, supplier, unit_price)`, `orders (id, customer_id, order_date, channel, region, status)`, `order_items (id, order_id, product_id, quantity, unit_price)`, `refunds (id, order_item_id, refund_date, reason, amount)`; constants `BAD_SUPPLIER`, `SUPPLIERS`, `CATEGORIES`, `REGIONS`; pytest fixture `dataset` (session scope, seed 42).

- [ ] **Step 1: Add the shared fixture to `backend/tests/conftest.py`** (append below the docstring)

```python
import pytest

from data.generate import generate


@pytest.fixture(scope="session")
def dataset():
    return generate(seed=42)
```

- [ ] **Step 2: Write the failing tests** (`backend/tests/test_generate.py`)

```python
from collections import Counter
from datetime import date

from data.generate import BAD_SUPPLIER, CATEGORIES, REGIONS, SUPPLIERS, generate


def _index(ds):
    products = {p[0]: p for p in ds.products}
    orders = {o[0]: o for o in ds.orders}
    return products, orders


def test_same_seed_gives_identical_data():
    a, b = generate(seed=42), generate(seed=42)
    assert a.orders == b.orders
    assert a.order_items == b.order_items
    assert a.refunds == b.refunds


def test_sizes(dataset):
    assert len(dataset.customers) == 2000
    assert len(dataset.products) == 120
    assert 9_900 <= len(dataset.orders) <= 10_100
    assert Counter(p[2] for p in dataset.products) == {c: 20 for c in CATEGORIES}
    assert Counter(p[3] for p in dataset.products) == {s: 15 for s in SUPPLIERS}
    assert {c[3] for c in dataset.customers} == set(REGIONS)


def test_values_are_consistent(dataset):
    products, orders = _index(dataset)
    assert len({c[2] for c in dataset.customers}) == len(dataset.customers)  # unique emails
    assert all(c[2].endswith("@example.com") for c in dataset.customers)
    assert all(date(2024, 1, 1) <= o[2] <= date(2025, 12, 31) for o in orders.values())
    items = {i[0]: i for i in dataset.order_items}
    for refund in dataset.refunds:
        item = items[refund[1]]
        assert orders[item[1]][5] == "completed"          # only completed orders are refunded
        assert refund[4] == round(item[4] * item[3], 2)   # full refund of the line
        assert refund[2] > orders[item[1]][2]             # refund after the order


def test_t1_holiday_spike(dataset):
    per_month = Counter((o[2].year, o[2].month) for o in dataset.orders)
    holiday = [n for (_, m), n in per_month.items() if m in (11, 12)]
    other = [n for (_, m), n in per_month.items() if m not in (11, 12)]
    assert (sum(holiday) / len(holiday)) >= 1.5 * (sum(other) / len(other))


def test_t2_bad_supplier_refund_rate(dataset):
    products, orders = _index(dataset)
    refunded = {r[1] for r in dataset.refunds}
    completed = [i for i in dataset.order_items if orders[i[1]][5] == "completed"]
    sold = Counter(products[i[2]][3] for i in completed)
    returned = Counter(products[i[2]][3] for i in completed if i[0] in refunded)
    rate = {s: returned[s] / sold[s] for s in sold}
    others = [r for s, r in rate.items() if s != BAD_SUPPLIER]
    assert rate[BAD_SUPPLIER] >= 2.5 * (sum(others) / len(others))


def test_t3_march_north_electronics_drop(dataset):
    products, orders = _index(dataset)

    def electronics_orders(in_region, year, month):
        return len({
            i[1] for i in dataset.order_items
            if products[i[2]][2] == "Electronics"
            and in_region(orders[i[1]][4])
            and (orders[i[1]][2].year, orders[i[1]][2].month) == (year, month)
        })

    def ratio(in_region):
        baseline = (electronics_orders(in_region, 2025, 2) + electronics_orders(in_region, 2025, 4)) / 2
        return electronics_orders(in_region, 2025, 3) / baseline

    assert ratio(lambda r: r == "North") <= 0.40
    assert ratio(lambda r: r != "North") >= 0.80
```

- [ ] **Step 3: Run the tests to see them fail**

Run (in `backend/`): `uv run pytest tests/test_generate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data.generate'`.

- [ ] **Step 4: Implement `data/generate.py`**

```python
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

REGIONS = ["North", "South", "East", "West"]
CATEGORY_PRICES = {
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

N_CUSTOMERS = 2000
PRODUCTS_PER_CATEGORY = 20
TARGET_ORDERS = 10_000
HOLIDAY_FACTOR = 1.8
CANCEL_RATE = 0.05
APP_SHARE = 0.4
BASE_REFUND_RATE = 0.05
BAD_SUPPLIER_REFUND_RATE = 0.15
STOCKOUT_DROP = 0.85  # share of North Electronics items removed in March 2025


@dataclass
class Dataset:
    customers: list[tuple] = field(default_factory=list)    # (id, full_name, email, region, signup_date, signup_channel)
    products: list[tuple] = field(default_factory=list)     # (id, name, category, supplier, unit_price)
    orders: list[tuple] = field(default_factory=list)       # (id, customer_id, order_date, channel, region, status)
    order_items: list[tuple] = field(default_factory=list)  # (id, order_id, product_id, quantity, unit_price)
    refunds: list[tuple] = field(default_factory=list)      # (id, order_item_id, refund_date, reason, amount)


def _months() -> list[tuple[int, int]]:
    return [(y, m) for y in (2024, 2025) for m in range(1, 13)]


def _month_days(year: int, month: int) -> int:
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days


def generate(seed: int = 42) -> Dataset:
    rng = random.Random(seed)
    ds = Dataset()

    # Customers (all signed up during 2023, before any order)
    for cid in range(1, N_CUSTOMERS + 1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        name = f"{first} {last}"
        email = f"{first}.{last}{cid}".lower().replace("'", "") + "@example.com"
        signup = date(2023, 1, 1) + timedelta(days=rng.randrange(365))
        ds.customers.append((cid, name, email, rng.choice(REGIONS), signup,
                             rng.choice(["web", "app"])))
    customer_region = {c[0]: c[3] for c in ds.customers}

    # Products: 20 per category, suppliers assigned round-robin
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

    # Orders: fixed count per month, Nov/Dec boosted (T1)
    months = _months()
    weights = [HOLIDAY_FACTOR if m in (11, 12) else 1.0 for _, m in months]
    base = TARGET_ORDERS / sum(weights)

    order_id = item_id = refund_id = 0
    for (year, month), weight in zip(months, weights):
        for _ in range(round(base * weight)):
            order_date = date(year, month, 1) + timedelta(days=rng.randrange(_month_days(year, month)))
            customer_id = rng.randint(1, N_CUSTOMERS)
            region = customer_region[customer_id]
            channel = "app" if rng.random() < APP_SHARE else "web"
            status = "cancelled" if rng.random() < CANCEL_RATE else "completed"

            items = []
            for _ in range(rng.choice([1, 1, 2, 2, 3, 4])):
                product = product_by_id[rng.choice(product_ids)]
                quantity = rng.choice([1, 1, 1, 2, 2, 3])
                stockout = (region == "North" and (year, month) == (2025, 3)
                            and product[2] == "Electronics")
                if stockout and rng.random() < STOCKOUT_DROP:
                    continue  # T3: item unavailable, never sold
                items.append((product, quantity))
            if not items:
                continue  # whole order lost to the stock-out

            order_id += 1
            ds.orders.append((order_id, customer_id, order_date, channel, region, status))
            for product, quantity in items:
                item_id += 1
                ds.order_items.append((item_id, order_id, product[0], quantity, product[4]))
                if status != "completed":
                    continue
                rate = BAD_SUPPLIER_REFUND_RATE if product[3] == BAD_SUPPLIER else BASE_REFUND_RATE
                if rng.random() < rate:  # T2
                    refund_id += 1
                    ds.refunds.append((refund_id, item_id,
                                       order_date + timedelta(days=rng.randint(3, 30)),
                                       rng.choice(REFUND_REASONS),
                                       round(product[4] * quantity, 2)))
    return ds
```
(Prototype run with seed 42: 10,005 orders, 21,600 items, 1,300 refunds; T1 = 1.80, T2 = 3.55×, T3 North = 0.14, other regions = 1.12.)

- [ ] **Step 5: Run the tests to see them pass**

Run (in `backend/`): `uv run pytest tests/test_generate.py -v`
Expected: 6 passed.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check . ../data
cd ..
git add data/generate.py backend/tests/conftest.py backend/tests/test_generate.py
git commit -m "feat(data): seeded synthetic generator with three planted trends"
```

---

### Task 4: Load data, read-only role, safe view and the setup command

**Files:**
- Create: `data/load_data.py`, `data/roles.py`, `data/setup_db.py`
- Modify: `backend/tests/conftest.py` (add the `loaded_db` fixture)
- Test: `backend/tests/test_load_and_roles.py`

**Interfaces:**
- Consumes: `reset_schema`, `apply_schema` (Task 2); `generate`, `Dataset` (Task 3); `Settings` (Task 1).
- Produces: `data.load_data.load_dataset(conn, ds: Dataset) -> dict[str, int]`; `data.roles.setup_roles(conn, ro_password: str, timeout: str = "5s") -> None`; `data.roles.READ_TABLES`; `python -m data.setup_db` command; pytest fixture `loaded_db` (session) → `{"admin_url": str, "ro_url": str}`.

- [ ] **Step 1: Add the `loaded_db` fixture to `backend/tests/conftest.py`** (append)

```python
import psycopg  # noqa: E402
from psycopg.conninfo import make_conninfo  # noqa: E402

from data.db_setup import apply_schema, reset_schema  # noqa: E402
from data.load_data import load_dataset  # noqa: E402
from data.roles import setup_roles  # noqa: E402
from tests.helpers import ensure_database  # noqa: E402

RO_PASSWORD = "analyst_ro_test"


@pytest.fixture(scope="session")
def loaded_db(dataset):
    admin_url = ensure_database("larkspur_test")
    with psycopg.connect(admin_url, autocommit=True) as conn:
        reset_schema(conn)
        apply_schema(conn)
        load_dataset(conn, dataset)
        setup_roles(conn, RO_PASSWORD, timeout="5s")
    ro_url = make_conninfo(admin_url, user="analyst_ro", password=RO_PASSWORD)
    return {"admin_url": admin_url, "ro_url": ro_url}
```

- [ ] **Step 2: Write the failing tests** (`backend/tests/test_load_and_roles.py`)

```python
import psycopg
import pytest
from psycopg import errors


def test_row_counts_match_dataset(loaded_db, dataset):
    with psycopg.connect(loaded_db["admin_url"]) as conn:
        for table in ("customers", "products", "orders", "order_items", "refunds"):
            (count,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            assert count == len(getattr(dataset, table)), table


def test_t3_visible_in_database(loaded_db):
    query = """
        SELECT EXTRACT(MONTH FROM o.order_date)::int AS m, COUNT(DISTINCT o.id)
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p ON p.id = oi.product_id
        WHERE o.region = 'North' AND p.category = 'Electronics'
          AND o.order_date >= '2025-02-01' AND o.order_date < '2025-05-01'
        GROUP BY 1
    """
    with psycopg.connect(loaded_db["admin_url"]) as conn:
        by_month = dict(conn.execute(query).fetchall())
    assert by_month[3] <= 0.40 * (by_month[2] + by_month[4]) / 2


def test_read_only_role_can_read_allowed_tables(loaded_db, dataset):
    with psycopg.connect(loaded_db["ro_url"]) as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM orders").fetchone()
        assert count == len(dataset.orders)
        cols = conn.execute("SELECT * FROM customers_safe LIMIT 1").description
        assert [c.name for c in cols] == ["id", "region", "signup_date", "signup_channel"]


@pytest.mark.parametrize("query", [
    "SELECT * FROM customers",
    "SELECT email FROM customers",
    "SELECT * FROM knowledge",
])
def test_read_only_role_cannot_read_private_tables(loaded_db, query):
    with psycopg.connect(loaded_db["ro_url"]) as conn:
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute(query)


@pytest.mark.parametrize("query", [
    "INSERT INTO orders VALUES (999999, 1, '2025-01-01', 'web', 'North', 'completed')",
    "UPDATE orders SET status = 'cancelled'",
    "DELETE FROM refunds",
    "DROP TABLE orders",
    "CREATE TABLE hack (id int)",
])
def test_read_only_role_cannot_write(loaded_db, query):
    with psycopg.connect(loaded_db["ro_url"]) as conn:
        with pytest.raises((errors.InsufficientPrivilege, errors.ReadOnlySqlTransaction)):
            conn.execute(query)


def test_read_only_role_has_timeout_and_read_only_default(loaded_db):
    with psycopg.connect(loaded_db["ro_url"]) as conn:
        assert conn.execute("SHOW statement_timeout").fetchone() == ("5s",)
        assert conn.execute("SHOW default_transaction_read_only").fetchone() == ("on",)
```

- [ ] **Step 3: Run the tests to see them fail**

Run (in `backend/`): `uv run pytest tests/test_load_and_roles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data.load_data'`.

- [ ] **Step 4: Implement `data/load_data.py`**

```python
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
    with conn.transaction():
        for table, columns in TABLE_COLUMNS.items():
            rows = getattr(ds, table)
            with conn.cursor() as cur:
                with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
                    for row in rows:
                        copy.write_row(row)
            counts[table] = len(rows)
    return counts
```

- [ ] **Step 5: Implement `data/roles.py`**

```python
"""Privacy view + read-only role used to run agent SQL."""
import psycopg
from psycopg import sql

READ_TABLES = ("customers_safe", "products", "orders", "order_items", "refunds")


def setup_roles(conn: psycopg.Connection, ro_password: str, timeout: str = "5s") -> None:
    conn.execute(
        "CREATE OR REPLACE VIEW customers_safe AS "
        "SELECT id, region, signup_date, signup_channel FROM customers"
    )
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'analyst_ro'").fetchone()
    verb = "ALTER" if exists else "CREATE"
    conn.execute(sql.SQL(verb + " ROLE analyst_ro WITH LOGIN PASSWORD {}").format(
        sql.Literal(ro_password)))
    conn.execute(sql.SQL("ALTER ROLE analyst_ro SET statement_timeout = {}").format(
        sql.Literal(timeout)))
    conn.execute("ALTER ROLE analyst_ro SET default_transaction_read_only = on")
    conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO analyst_ro").format(
        sql.Identifier(conn.info.dbname)))
    conn.execute("GRANT USAGE ON SCHEMA public TO analyst_ro")
    conn.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM analyst_ro")
    for table in READ_TABLES:
        conn.execute(sql.SQL("GRANT SELECT ON {} TO analyst_ro").format(sql.Identifier(table)))
```

- [ ] **Step 6: Implement `data/setup_db.py`**

```python
"""Build the development database from scratch.

Usage (from the repo root):  uv run --project backend python -m data.setup_db
WARNING: drops and recreates everything in schema public.
"""
import psycopg

from app.config import get_settings
from data.db_setup import apply_schema, reset_schema
from data.generate import generate
from data.load_data import load_dataset
from data.roles import setup_roles


def main() -> None:
    settings = get_settings()
    with psycopg.connect(settings.database_url_admin, autocommit=True) as conn:
        reset_schema(conn)
        apply_schema(conn)
        counts = load_dataset(conn, generate(seed=42))
        setup_roles(conn, settings.analyst_ro_password, settings.sql_timeout)
    print("Loaded:", counts)


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run the tests to see them pass**

Run (in `backend/`): `uv run pytest -v`
Expected: all tests pass (Tasks 1–4: 2 + 4 + 6 + 12 = 24 passed).

- [ ] **Step 8: Build the dev database once by hand**

Run (from the repo root): `uv run --project backend python -m data.setup_db`
Expected output: `Loaded: {'customers': 2000, 'products': 120, 'orders': 10005, 'order_items': 21600, 'refunds': 1300}`

- [ ] **Step 9: Lint and commit**

```bash
cd backend && uv run ruff check . ../data && cd ..
git add data/load_data.py data/roles.py data/setup_db.py backend/tests/conftest.py backend/tests/test_load_and_roles.py
git commit -m "feat(data): COPY loader, read-only role, customers_safe view, setup command"
```

---

### ✅ Milestone 1 checkpoint: Data (human + Claude, no code)

- [ ] **Walkthrough (Claude explains in plain language):** synthetic data and why we use a **fixed seed**; the 3 planted trends as **ground truth**; why the T3 stock-out *removes* sales instead of replacing them (so revenue really drops); `COPY` vs. row-by-row `INSERT`; foreign keys and load order; the **least-privilege** role, the `customers_safe` view, `default_transaction_read_only` and `statement_timeout`; indexes and what they speed up.
- [ ] **Quiz (one question at a time, wait for each answer):**
  1. Why does the generator use a fixed seed, and what would break without it?
  2. How would you prove to an interviewer that the March drop is real in your data?
  3. If the LLM writes `SELECT email FROM customers`, what stops it, and at which layer?
  4. Why is `full_name` kept in the database at all if nobody can query it?
  5. What does an index on `orders(order_date)` speed up, and what does it cost?
- [ ] **Create `DECISIONS.md`** with:
```markdown
# Design decisions

## Synthetic data with planted trends
Real shop data is private, so I generate it with a fixed seed (42) for reproducibility and inject three known patterns (holiday spike, a high-refund supplier, a March stock-out in the North). They are my ground truth for testing the agent.

## Least-privilege database role
Agent SQL runs as `analyst_ro`: SELECT only on five objects, read-only transactions by default, 5 s statement timeout. Personal data lives only in `customers`, which the role cannot read; it sees the `customers_safe` view instead. Safety is enforced by the database, not by the prompt.

## Indexes
B-tree indexes on the columns used for filtering and joining (dates, region, foreign keys, category, supplier) keep aggregation queries fast as data grows.
```
- [ ] **Commit:** `git add DECISIONS.md && git commit -m "docs: milestone 1 decisions"`

---

### Task 5: Knowledge base sources

**Files:**
- Create: `data/knowledge/dictionary.yaml`, `data/knowledge/glossary.yaml`, `data/knowledge/examples.yaml`
- Create: `data/knowledge_entries.py`
- Test: `backend/tests/test_knowledge_entries.py`

**Interfaces:**
- Consumes: `loaded_db` fixture, `READ_TABLES` (Task 4).
- Produces: `data.knowledge_entries.KnowledgeEntry(kind: str, title: str, content: str)` (frozen dataclass); `load_entries(directory: Path = KNOWLEDGE_DIR) -> list[KnowledgeEntry]`; `load_examples(directory: Path = KNOWLEDGE_DIR) -> list[dict]` (keys `question`, `sql`).

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_knowledge_entries.py`)

```python
from collections import Counter

import psycopg
import pytest

from data.knowledge_entries import load_entries, load_examples
from data.roles import READ_TABLES


def test_entry_counts_by_kind():
    counts = Counter(e.kind for e in load_entries())
    assert counts == {"dictionary": 5, "glossary": 9, "example": 15}


def test_titles_are_unique_and_content_not_empty():
    entries = load_entries()
    assert len({e.title for e in entries}) == len(entries)
    assert all(e.content.strip() for e in entries)


def test_dictionary_covers_exactly_the_readable_tables():
    titles = {e.title for e in load_entries() if e.kind == "dictionary"}
    assert titles == set(READ_TABLES)


def test_example_content_contains_question_and_sql():
    for entry in (e for e in load_entries() if e.kind == "example"):
        assert entry.content.startswith(f"Question: {entry.title}\nSQL:\n")


@pytest.mark.parametrize("example", load_examples(), ids=lambda e: e["question"][:40])
def test_every_example_sql_runs_as_read_only_role(loaded_db, example):
    with psycopg.connect(loaded_db["ro_url"]) as conn:
        rows = conn.execute(example["sql"]).fetchall()
    assert rows, "example query returned no rows"
```

- [ ] **Step 2: Run the tests to see them fail**

Run (in `backend/`): `uv run pytest tests/test_knowledge_entries.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'data.knowledge_entries'`.

- [ ] **Step 3: Create `data/knowledge/dictionary.yaml`**

```yaml
- title: orders
  content: |
    Table orders: one row per checkout at Larkspur Market.
    Columns: id (integer, primary key); customer_id (integer, joins customers_safe.id);
    order_date (date, from 2024-01-01 to 2025-12-31); channel (text: 'web' or 'app');
    region (text: 'North', 'South', 'East', 'West' - the customer's region);
    status (text: 'completed' or 'cancelled'; sales and revenue only count 'completed' orders).
    Join order lines with order_items.order_id = orders.id.
- title: order_items
  content: |
    Table order_items: one row per product line inside an order.
    Columns: id (integer, primary key); order_id (integer, joins orders.id);
    product_id (integer, joins products.id); quantity (integer, units bought);
    unit_price (numeric, price paid per unit at order time).
    Line revenue = quantity * unit_price. Units sold = SUM(quantity).
- title: products
  content: |
    Table products: the product catalogue (120 products).
    Columns: id (integer, primary key); name (text, e.g. 'Electronics Item 01');
    category (text: 'Electronics', 'Home', 'Fashion', 'Beauty', 'Sports', 'Grocery');
    supplier (text: 'Brightline Goods', 'Copperleaf Trading', 'Harbor & Pine Co',
    'Meridian Wholesale', 'Oakridge Partners', 'Silverstream Supply', 'Tidewater Imports',
    'Willow Lane Makers'); unit_price (numeric, current list price).
- title: refunds
  content: |
    Table refunds: one row per refunded order line (an order item is refunded at most once).
    Columns: id (integer, primary key); order_item_id (integer, joins order_items.id);
    refund_date (date); reason (text: 'damaged', 'wrong item', 'not as described',
    'changed mind', 'late delivery'); amount (numeric, money returned to the customer).
- title: customers_safe
  content: |
    View customers_safe: customers without personal data (names and emails are not available).
    Columns: id (integer, primary key, joins orders.customer_id); region (text: 'North',
    'South', 'East', 'West'); signup_date (date, during 2023); signup_channel (text: 'web' or 'app').
```

- [ ] **Step 4: Create `data/knowledge/glossary.yaml`**

```yaml
- title: Gross revenue (sales)
  content: |
    Gross revenue (also "sales" or "revenue") = SUM(order_items.quantity * order_items.unit_price)
    over order items whose order has status = 'completed'.
- title: Net revenue
  content: |
    Net revenue = gross revenue minus refunds: SUM(order_items.quantity * order_items.unit_price)
    for completed orders, minus SUM(refunds.amount) for refunds on those order items.
- title: Average order value (AOV)
  content: |
    Average order value (AOV) = gross revenue / COUNT(DISTINCT orders.id), using only
    orders with status = 'completed'.
- title: Refund rate
  content: |
    Refund rate = number of refunded order items / number of order items in completed orders.
    LEFT JOIN refunds ON refunds.order_item_id = order_items.id and count refunds.id.
- title: Cancellation rate
  content: |
    Cancellation rate = orders with status = 'cancelled' / all orders.
- title: Order count
  content: |
    Order count = COUNT(DISTINCT orders.id) with status = 'completed', unless the question
    explicitly asks about cancelled or all orders.
- title: Units sold
  content: |
    Units sold = SUM(order_items.quantity) over items in completed orders.
- title: Active customer
  content: |
    Active customer (for a period) = a customer with at least one completed order in that period:
    COUNT(DISTINCT orders.customer_id).
- title: Monthly trend
  content: |
    For trends over time group by DATE_TRUNC('month', orders.order_date) and order by that month.
    Quarters: DATE_TRUNC('quarter', orders.order_date).
```

- [ ] **Step 5: Create `data/knowledge/examples.yaml`**

```yaml
- question: How many completed orders were there in 2024?
  sql: |
    SELECT COUNT(*) AS completed_orders
    FROM orders
    WHERE status = 'completed' AND order_date >= '2024-01-01' AND order_date < '2025-01-01';
- question: What is gross revenue by region?
  sql: |
    SELECT o.region, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS gross_revenue
    FROM orders o JOIN order_items oi ON oi.order_id = o.id
    WHERE o.status = 'completed'
    GROUP BY o.region ORDER BY gross_revenue DESC;
- question: What are the top 5 products by units sold?
  sql: |
    SELECT p.name, SUM(oi.quantity) AS units_sold
    FROM order_items oi
    JOIN orders o ON o.id = oi.order_id
    JOIN products p ON p.id = oi.product_id
    WHERE o.status = 'completed'
    GROUP BY p.name ORDER BY units_sold DESC LIMIT 5;
- question: How many completed orders were there each month in 2025?
  sql: |
    SELECT DATE_TRUNC('month', order_date)::date AS month, COUNT(*) AS orders
    FROM orders
    WHERE status = 'completed' AND order_date >= '2025-01-01' AND order_date < '2026-01-01'
    GROUP BY 1 ORDER BY 1;
- question: What is the average order value by channel?
  sql: |
    SELECT o.channel,
           ROUND(SUM(oi.quantity * oi.unit_price) / COUNT(DISTINCT o.id), 2) AS aov
    FROM orders o JOIN order_items oi ON oi.order_id = o.id
    WHERE o.status = 'completed'
    GROUP BY o.channel;
- question: What is the refund rate by product category?
  sql: |
    SELECT p.category,
           ROUND(COUNT(r.id)::numeric / COUNT(oi.id), 4) AS refund_rate
    FROM order_items oi
    JOIN orders o ON o.id = oi.order_id
    JOIN products p ON p.id = oi.product_id
    LEFT JOIN refunds r ON r.order_item_id = oi.id
    WHERE o.status = 'completed'
    GROUP BY p.category ORDER BY refund_rate DESC;
- question: How many customers signed up through each channel?
  sql: |
    SELECT signup_channel, COUNT(*) AS customers
    FROM customers_safe
    GROUP BY signup_channel;
- question: What is gross revenue by category in the West region?
  sql: |
    SELECT p.category, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS gross_revenue
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.id
    JOIN products p ON p.id = oi.product_id
    WHERE o.status = 'completed' AND o.region = 'West'
    GROUP BY p.category ORDER BY gross_revenue DESC;
- question: What is gross revenue by supplier?
  sql: |
    SELECT p.supplier, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS gross_revenue
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.id
    JOIN products p ON p.id = oi.product_id
    WHERE o.status = 'completed'
    GROUP BY p.supplier ORDER BY gross_revenue DESC;
- question: What was the cancellation rate each month in 2024?
  sql: |
    SELECT DATE_TRUNC('month', order_date)::date AS month,
           ROUND(AVG(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END), 4) AS cancellation_rate
    FROM orders
    WHERE order_date >= '2024-01-01' AND order_date < '2025-01-01'
    GROUP BY 1 ORDER BY 1;
- question: What was net revenue in Q1 2025?
  sql: |
    SELECT ROUND(SUM(oi.quantity * oi.unit_price) - COALESCE(SUM(r.amount), 0), 2) AS net_revenue
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.id
    LEFT JOIN refunds r ON r.order_item_id = oi.id
    WHERE o.status = 'completed' AND o.order_date >= '2025-01-01' AND o.order_date < '2025-04-01';
- question: What are the most common refund reasons?
  sql: |
    SELECT reason, COUNT(*) AS refunds
    FROM refunds
    GROUP BY reason ORDER BY refunds DESC;
- question: How many completed orders came from each region and channel?
  sql: |
    SELECT region, channel, COUNT(*) AS orders
    FROM orders
    WHERE status = 'completed'
    GROUP BY region, channel ORDER BY region, channel;
- question: What is the average quantity per order line by category?
  sql: |
    SELECT p.category, ROUND(AVG(oi.quantity), 2) AS avg_quantity
    FROM order_items oi JOIN products p ON p.id = oi.product_id
    GROUP BY p.category ORDER BY avg_quantity DESC;
- question: How many active customers were there in each quarter of 2024?
  sql: |
    SELECT DATE_TRUNC('quarter', order_date)::date AS quarter,
           COUNT(DISTINCT customer_id) AS active_customers
    FROM orders
    WHERE status = 'completed' AND order_date >= '2024-01-01' AND order_date < '2025-01-01'
    GROUP BY 1 ORDER BY 1;
```

- [ ] **Step 6: Implement `data/knowledge_entries.py`**

```python
"""Read the knowledge-base YAML sources (metadata about the data, never the data itself)."""
from dataclasses import dataclass
from pathlib import Path

import yaml

KNOWLEDGE_DIR = Path(__file__).with_name("knowledge")


@dataclass(frozen=True)
class KnowledgeEntry:
    kind: str     # "dictionary" | "glossary" | "example"
    title: str
    content: str


def _read(directory: Path, name: str) -> list[dict]:
    return yaml.safe_load((directory / name).read_text(encoding="utf-8"))


def load_examples(directory: Path = KNOWLEDGE_DIR) -> list[dict]:
    return _read(directory, "examples.yaml")


def load_entries(directory: Path = KNOWLEDGE_DIR) -> list[KnowledgeEntry]:
    entries = [KnowledgeEntry("dictionary", d["title"], d["content"].strip())
               for d in _read(directory, "dictionary.yaml")]
    entries += [KnowledgeEntry("glossary", g["title"], g["content"].strip())
                for g in _read(directory, "glossary.yaml")]
    entries += [KnowledgeEntry("example", e["question"],
                               f"Question: {e['question']}\nSQL:\n{e['sql'].strip()}")
                for e in load_examples(directory)]
    return entries
```

- [ ] **Step 7: Run the tests to see them pass**

Run (in `backend/`): `uv run pytest tests/test_knowledge_entries.py -v`
Expected: 19 passed (4 + 15 examples).

- [ ] **Step 8: Commit**

```bash
cd ..
git add data/knowledge data/knowledge_entries.py backend/tests/test_knowledge_entries.py
git commit -m "feat(knowledge): data dictionary, glossary and verified example SQL"
```

---

### Task 6: Embeddings, knowledge loading and semantic search

**Files:**
- Create: `backend/app/knowledge/__init__.py` (empty), `backend/app/knowledge/embed.py`, `backend/app/knowledge/search.py`, `data/load_knowledge.py`
- Modify: `data/setup_db.py` (load knowledge), `backend/tests/conftest.py` (add `embedder`, `knowledge_db`)
- Test: `backend/tests/test_knowledge_search.py`

**Interfaces:**
- Consumes: `load_entries()`, `KnowledgeEntry` (Task 5); `loaded_db` (Task 4); `Settings.embedding_model` (Task 1).
- Produces: `app.knowledge.embed.Embedder(model_name: str = "BAAI/bge-small-en-v1.5")` with `embed_passages(texts: list[str]) -> list[np.ndarray]` and `embed_query(text: str) -> np.ndarray`; `app.knowledge.search.KnowledgeHit(kind, title, content, score: float)`; `search_knowledge(conn, embedder, query: str, k: int = 5) -> list[KnowledgeHit]`; `data.load_knowledge.entry_text(entry) -> str`, `load_knowledge(conn, entries, embedder) -> int`; fixtures `embedder` and `knowledge_db` (session).

- [ ] **Step 1: Add fixtures to `backend/tests/conftest.py`** (append)

```python
from app.knowledge.embed import Embedder  # noqa: E402
from data.knowledge_entries import load_entries  # noqa: E402
from data.load_knowledge import load_knowledge  # noqa: E402


@pytest.fixture(scope="session")
def embedder():
    return Embedder()  # downloads ~70 MB on first run, cached afterwards


@pytest.fixture(scope="session")
def knowledge_db(loaded_db, embedder):
    with psycopg.connect(loaded_db["admin_url"], autocommit=True) as conn:
        load_knowledge(conn, load_entries(), embedder)
    return loaded_db
```

- [ ] **Step 2: Write the failing tests** (`backend/tests/test_knowledge_search.py`)

```python
import psycopg

from app.knowledge.search import search_knowledge
from data.knowledge_entries import KnowledgeEntry
from data.load_knowledge import entry_text


def _titles(hits):
    return [h.title for h in hits]


def test_embedder_returns_384_dims(embedder):
    assert embedder.embed_query("revenue").shape == (384,)
    assert [v.shape for v in embedder.embed_passages(["a", "b"])] == [(384,), (384,)]


def test_entry_text_format():
    assert entry_text(KnowledgeEntry("glossary", "Units sold", "SUM(quantity)")) == "Units sold\nSUM(quantity)"
    example = KnowledgeEntry("example", "Q?", "Question: Q?\nSQL:\nSELECT 1")
    assert entry_text(example) == "Question: Q?\nSQL:\nSELECT 1"


def test_all_entries_loaded(knowledge_db):
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM knowledge").fetchone() == (29,)


def test_revenue_finds_gross_revenue_definition(knowledge_db, embedder):
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        hits = search_knowledge(conn, embedder, "revenue")
    assert "Gross revenue (sales)" in _titles(hits)


def test_aov_is_top_hit(knowledge_db, embedder):
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        hits = search_knowledge(conn, embedder, "average order value")
    assert hits[0].title == "Average order value (AOV)"


def test_supplier_question_finds_products_table(knowledge_db, embedder):
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        hits = search_knowledge(conn, embedder, "which table has the supplier?")
    assert hits[0].kind == "dictionary" and hits[0].title == "products"


def test_k_and_score_order(knowledge_db, embedder):
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        hits = search_knowledge(conn, embedder, "orders by month", k=3)
    assert len(hits) == 3
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(isinstance(s, float) for s in scores)


def test_blank_query_returns_nothing(knowledge_db, embedder):
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        assert search_knowledge(conn, embedder, "   ") == []
```

- [ ] **Step 3: Run the tests to see them fail**

Run (in `backend/`): `uv run pytest tests/test_knowledge_search.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'app.knowledge'`.

- [ ] **Step 4: Implement `backend/app/knowledge/embed.py`** (and the empty `backend/app/knowledge/__init__.py`)

```python
"""Text embeddings with FastEmbed (BAAI/bge-small-en-v1.5, 384 dimensions, runs locally)."""
import numpy as np
from fastembed import TextEmbedding

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self._model = TextEmbedding(model_name)

    def embed_passages(self, texts: list[str]) -> list[np.ndarray]:
        """For documents stored in the knowledge base."""
        return list(self._model.passage_embed(texts))

    def embed_query(self, text: str) -> np.ndarray:
        """For a user question (BGE adds its query instruction)."""
        return next(iter(self._model.query_embed([text])))
```

- [ ] **Step 5: Implement `data/load_knowledge.py`**

```python
"""Embed knowledge entries and (re)fill the knowledge table."""
import psycopg
from pgvector.psycopg import register_vector

from app.knowledge.embed import Embedder
from data.knowledge_entries import KnowledgeEntry


def entry_text(entry: KnowledgeEntry) -> str:
    """Text that gets embedded. Example content already starts with its question."""
    return entry.content if entry.kind == "example" else f"{entry.title}\n{entry.content}"


def load_knowledge(conn: psycopg.Connection, entries: list[KnowledgeEntry],
                   embedder: Embedder) -> int:
    register_vector(conn)
    vectors = embedder.embed_passages([entry_text(e) for e in entries])
    with conn.transaction():
        conn.execute("TRUNCATE knowledge RESTART IDENTITY")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO knowledge (kind, title, content, embedding) VALUES (%s, %s, %s, %s)",
                [(e.kind, e.title, e.content, v) for e, v in zip(entries, vectors)],
            )
    return len(entries)
```

- [ ] **Step 6: Implement `backend/app/knowledge/search.py`**

```python
"""Semantic search over the knowledge table (cosine similarity via pgvector)."""
from dataclasses import dataclass

import psycopg
from pgvector.psycopg import register_vector

from app.knowledge.embed import Embedder


@dataclass(frozen=True)
class KnowledgeHit:
    kind: str
    title: str
    content: str
    score: float  # cosine similarity, higher = more relevant


def search_knowledge(conn: psycopg.Connection, embedder: Embedder, query: str,
                     k: int = 5) -> list[KnowledgeHit]:
    if not query.strip():
        return []
    register_vector(conn)
    vector = embedder.embed_query(query)
    rows = conn.execute(
        "SELECT kind, title, content, 1 - (embedding <=> %s) AS score "
        "FROM knowledge ORDER BY embedding <=> %s LIMIT %s",
        (vector, vector, k),
    ).fetchall()
    return [KnowledgeHit(kind, title, content, float(score)) for kind, title, content, score in rows]
```

- [ ] **Step 7: Make `data/setup_db.py` load the knowledge base too** (replace the file)

```python
"""Build the development database from scratch.

Usage (from the repo root):  uv run --project backend python -m data.setup_db
WARNING: drops and recreates everything in schema public.
"""
import psycopg

from app.config import get_settings
from app.knowledge.embed import Embedder
from data.db_setup import apply_schema, reset_schema
from data.generate import generate
from data.knowledge_entries import load_entries
from data.load_data import load_dataset
from data.load_knowledge import load_knowledge
from data.roles import setup_roles


def main() -> None:
    settings = get_settings()
    with psycopg.connect(settings.database_url_admin, autocommit=True) as conn:
        reset_schema(conn)
        apply_schema(conn)
        counts = load_dataset(conn, generate(seed=42))
        setup_roles(conn, settings.analyst_ro_password, settings.sql_timeout)
        counts["knowledge"] = load_knowledge(conn, load_entries(), Embedder(settings.embedding_model))
    print("Loaded:", counts)


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Run all tests**

Run (in `backend/`): `uv run pytest -v`
Expected: all pass (the first run downloads the embedding model; on Windows a harmless "symlinks" warning may appear).

- [ ] **Step 9: Rebuild the dev database and commit**

```bash
cd ..
uv run --project backend python -m data.setup_db
```
Expected: `Loaded: {... 'knowledge': 29}`
```bash
cd backend && uv run ruff check . ../data && cd ..
git add backend/app/knowledge data/load_knowledge.py data/setup_db.py backend/tests/conftest.py backend/tests/test_knowledge_search.py
git commit -m "feat(knowledge): FastEmbed embeddings, pgvector loading and semantic search"
```

---

### ✅ Milestone 2 checkpoint: Knowledge (human + Claude, no code)

- [ ] **Walkthrough:** RAG over **metadata, not data** (why the agent never searches order rows); the 3 kinds of knowledge; embeddings and cosine similarity (Chapter 3 of your notes); passage vs. query embedding (the BGE instruction prefix); pgvector's `<=>` operator; why 29 entries need no vector index; why example SQL is tested against the real database as `analyst_ro`; why eval questions must not appear in the examples.
- [ ] **Quiz (one at a time):**
  1. What exactly does `search_knowledge` return for "average order value", and why is that useful to the LLM?
  2. Why embed table *descriptions* instead of the actual order rows?
  3. What does `1 - (embedding <=> query)` compute?
  4. When would you add an HNSW index to the knowledge table?
  5. Why does each example's SQL have a test that runs it as the read-only role?
- [ ] **Append to `DECISIONS.md`:**
```markdown
## RAG over metadata, never data
The knowledge base holds a data dictionary, business glossary and 15 verified question→SQL examples (29 entries), embedded with BAAI/bge-small-en-v1.5 (384-d, FastEmbed, runs locally, no API cost) and stored in pgvector next to the shop data. The agent retrieves the top 5 to learn the schema and definitions; it gets real numbers only by running SQL. Every example query is tested against the database, so the agent is never taught broken SQL.

## pgvector instead of a dedicated vector DB
29 vectors fit in one Postgres; an extra service would add cost and sync problems for no gain. I'd revisit at millions of vectors.
```
- [ ] **Commit:** `git add DECISIONS.md && git commit -m "docs: milestone 2 decisions"`

---

### Task 7: SQL validator

**Files:**
- Create: `backend/app/sql/__init__.py` (empty), `backend/app/sql/validator.py`
- Test: `backend/tests/test_validator.py`

**Interfaces:**
- Consumes: `load_examples()` (Task 5).
- Produces: `app.sql.validator.ValidationResult(ok: bool, sql: str | None = None, error: str | None = None)` (frozen dataclass); `validate_sql(sql: str, max_rows: int = 200) -> ValidationResult`; constants `ALLOWED_TABLES`, `MAX_ROWS`.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_validator.py`)

```python
import pytest

from app.sql.validator import validate_sql
from data.knowledge_entries import load_examples

ALLOWED = [
    "SELECT region, COUNT(*) FROM orders GROUP BY region",
    "WITH m AS (SELECT DATE_TRUNC('month', order_date) AS mo, COUNT(*) c FROM orders GROUP BY 1) "
    "SELECT * FROM m ORDER BY mo",
    "SELECT id FROM orders UNION SELECT id FROM refunds",
    "SELECT * FROM public.orders",
    "SELECT * FROM orders o JOIN order_items i ON i.order_id = o.id "
    "JOIN products p ON p.id = i.product_id WHERE p.category = 'Electronics'",
    "SELECT * FROM customers_safe",
]

BLOCKED = [
    ("DROP TABLE orders", "Only SELECT"),
    ("DELETE FROM orders", "Only SELECT"),
    ("INSERT INTO orders VALUES (1)", "Only SELECT"),
    ("UPDATE orders SET status = 'x'", "Only SELECT"),
    ("COPY orders TO '/tmp/x'", "Only SELECT"),
    ("SELECT 1; DROP TABLE orders", "one SQL statement"),
    ("SELECT * FROM customers", "Table not allowed"),
    ("SELECT id FROM orders WHERE customer_id IN (SELECT id FROM customers)", "Table not allowed"),
    ("SELECT * FROM pg_catalog.pg_tables", "Table not allowed"),
    ("SELECT * FROM information_schema.tables", "Table not allowed"),
    ("SELECT * INTO newtab FROM orders", "Forbidden operation"),
    ("SELECT * FROM orders FOR UPDATE", "Forbidden operation"),
    ("SELECT pg_sleep(10)", "Function not allowed"),
    ("SELECT set_config('statement_timeout', '0', false)", "Function not allowed"),
    ("SELECT * FROM generate_series(1, 10)", "Table functions"),
    ("SELEC * FROM orders", "Could not parse"),
    ("", "Empty query"),
    ("   \n  ", "Empty query"),
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_allowed_queries_pass(sql):
    result = validate_sql(sql)
    assert result.ok, result.error
    assert result.error is None


@pytest.mark.parametrize("sql,reason", BLOCKED)
def test_blocked_queries_are_rejected(sql, reason):
    result = validate_sql(sql)
    assert not result.ok
    assert result.sql is None
    assert reason in result.error


def test_missing_limit_is_added():
    assert validate_sql("SELECT * FROM orders").sql == "SELECT * FROM orders LIMIT 200"


def test_small_limit_is_kept():
    assert validate_sql("select * from orders limit 10").sql == "SELECT * FROM orders LIMIT 10"


def test_large_limit_is_capped():
    assert validate_sql("SELECT * FROM orders LIMIT 5000").sql == "SELECT * FROM orders LIMIT 200"


def test_union_is_wrapped_and_limited():
    sql = validate_sql("SELECT id FROM orders UNION SELECT id FROM refunds").sql
    assert sql == "SELECT * FROM (SELECT id FROM orders UNION SELECT id FROM refunds) AS q LIMIT 200"


def test_custom_max_rows():
    assert validate_sql("SELECT * FROM orders", max_rows=5).sql.endswith("LIMIT 5")


@pytest.mark.parametrize("example", load_examples(), ids=lambda e: e["question"][:40])
def test_all_knowledge_examples_pass_validator(example):
    assert validate_sql(example["sql"]).ok
```

- [ ] **Step 2: Run the tests to see them fail**

Run (in `backend/`): `uv run pytest tests/test_validator.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'app.sql'`.

- [ ] **Step 3: Implement `backend/app/sql/validator.py`** (and the empty `backend/app/sql/__init__.py`)

```python
"""SQL validator: only a single, read-only SELECT over allowed tables gets through."""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

ALLOWED_TABLES = frozenset({"customers_safe", "products", "orders", "order_items", "refunds"})
MAX_ROWS = 200
_QUERY_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)
_FORBIDDEN_NODE_NAMES = (
    "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter", "AlterTable",
    "TruncateTable", "Copy", "Grant", "Revoke", "Command", "Into", "Set", "Lock",
)
_FORBIDDEN_NODES = tuple(getattr(exp, n) for n in _FORBIDDEN_NODE_NAMES if hasattr(exp, n))
_FORBIDDEN_FUNCTIONS = frozenset({
    "set_config", "pg_sleep", "pg_sleep_for", "pg_sleep_until", "pg_terminate_backend",
    "pg_cancel_backend", "pg_reload_conf", "pg_read_file", "pg_read_binary_file",
    "pg_ls_dir", "lo_import", "lo_export", "dblink", "dblink_exec",
})


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    sql: str | None = None    # the (possibly LIMIT-adjusted) SQL to execute
    error: str | None = None


def _reject(reason: str) -> ValidationResult:
    return ValidationResult(ok=False, error=reason)


def validate_sql(sql: str, max_rows: int = MAX_ROWS) -> ValidationResult:
    if not sql or not sql.strip():
        return _reject("Empty query.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError as e:
        return _reject(f"Could not parse SQL: {str(e).splitlines()[0]}")
    if len(statements) != 1:
        return _reject("Exactly one SQL statement is allowed.")
    tree = statements[0]

    if not isinstance(tree, _QUERY_ROOTS):
        return _reject("Only SELECT queries are allowed.")
    for node in tree.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            return _reject(f"Forbidden operation: {type(node).__name__}.")
        if isinstance(node, exp.Func):
            name = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()
            if name in _FORBIDDEN_FUNCTIONS:
                return _reject(f"Function not allowed: {name}.")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        schema = (table.db or "").lower()
        if not name:
            return _reject("Table functions are not allowed in FROM.")
        if name in cte_names and not schema:
            continue
        if schema not in ("", "public") or name not in ALLOWED_TABLES:
            return _reject(f"Table not allowed: {table.sql(dialect='postgres')}. "
                           f"Allowed tables: {', '.join(sorted(ALLOWED_TABLES))}.")

    limit = tree.args.get("limit")
    current = None
    if limit is not None and isinstance(limit.expression, exp.Literal) and limit.expression.is_int:
        current = int(limit.expression.this)
    if current is None or current > max_rows:
        if isinstance(tree, exp.Select):
            tree = tree.limit(max_rows)
        else:  # set operation: wrap so the LIMIT applies to the whole result
            tree = exp.select("*").from_(tree.subquery("q")).limit(max_rows)
    return ValidationResult(ok=True, sql=tree.sql(dialect="postgres"))
```
(Prototyped against sqlglot 30.21.0: every case in the test lists behaves as asserted.)

- [ ] **Step 4: Run the tests to see them pass**

Run (in `backend/`): `uv run pytest tests/test_validator.py -v`
Expected: all pass (6 + 18 + 5 + 15 = 44).

- [ ] **Step 5: Commit**

```bash
uv run ruff check .
cd ..
git add backend/app/sql backend/tests/test_validator.py
git commit -m "feat(sql): sqlglot validator for single read-only SELECTs with row cap"
```

---

### Task 8: Connection pool and SQL executor

**Files:**
- Create: `backend/app/db.py`, `backend/app/sql/executor.py`
- Test: `backend/tests/test_executor.py`

**Interfaces:**
- Consumes: `validate_sql`, `ValidationResult` (Task 7); `loaded_db` (Task 4).
- Produces: `app.db.make_pool(conninfo: str, min_size: int = 1, max_size: int = 5) -> psycopg_pool.ConnectionPool`; `app.sql.executor.SqlResult(ok: bool, sql: str | None = None, columns: list[str] = [], rows: list[list] = [], row_count: int = 0, error: str | None = None)` with `to_dict() -> dict`; `run_select(pool, sql: str, *, max_rows: int = 200, timeout: str = "5s") -> SqlResult`. Rows contain only JSON-safe values (Decimal → float, date/datetime → ISO string).

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_executor.py`)

```python
import pytest

from app.db import make_pool
from app.sql.executor import run_select


@pytest.fixture(scope="module")
def pool(loaded_db):
    p = make_pool(loaded_db["ro_url"], min_size=1, max_size=1)
    yield p
    p.close()


def test_simple_query(pool, dataset):
    result = run_select(pool, "SELECT COUNT(*) AS n FROM orders")
    assert result.ok and result.error is None
    assert result.columns == ["n"]
    assert result.rows == [[len(dataset.orders)]]
    assert result.row_count == 1
    assert result.sql.endswith("LIMIT 200")


def test_values_are_json_safe(pool):
    result = run_select(pool, "SELECT order_date, unit_price FROM orders o "
                              "JOIN order_items i ON i.order_id = o.id ORDER BY i.id LIMIT 1")
    date_value, price_value = result.rows[0]
    assert isinstance(date_value, str) and len(date_value) == 10   # 'YYYY-MM-DD'
    assert isinstance(price_value, float)


def test_rows_are_capped(pool):
    result = run_select(pool, "SELECT * FROM order_items")
    assert result.ok and result.row_count == 200 and len(result.rows) == 200


def test_rejected_query_never_runs(pool):
    result = run_select(pool, "DROP TABLE orders")
    assert not result.ok
    assert result.error.startswith("Rejected:")
    assert result.sql is None


def test_database_error_is_reported(pool):
    result = run_select(pool, "SELECT no_such_column FROM orders")
    assert not result.ok
    assert result.error.startswith("Database error:")
    assert "no_such_column" in result.error


def test_timeout_is_reported_and_pool_recovers(pool):
    slow = run_select(pool, "SELECT COUNT(*) FROM order_items a, order_items b", timeout="200ms")
    assert not slow.ok
    assert "timed out" in slow.error
    assert run_select(pool, "SELECT 1 AS one").rows == [[1]]


def test_pool_resets_session_settings(pool):
    with pool.connection() as conn:
        conn.execute("SET statement_timeout = '1ms'")
    with pool.connection() as conn:   # same single connection, after reset
        assert conn.execute("SHOW statement_timeout").fetchone() == ("5s",)


def test_to_dict_shape(pool):
    d = run_select(pool, "SELECT 1 AS one").to_dict()
    assert set(d) == {"ok", "sql", "columns", "rows", "row_count", "error"}
```

- [ ] **Step 2: Run the tests to see them fail**

Run (in `backend/`): `uv run pytest tests/test_executor.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'app.db'`.

- [ ] **Step 3: Implement `backend/app/db.py`**

```python
"""Connection pools. Each connection is reset when it goes back to the pool."""
import psycopg
from psycopg_pool import ConnectionPool


def _reset(conn: psycopg.Connection) -> None:
    conn.execute("RESET ALL")  # undo any session-level SET made while borrowed


def make_pool(conninfo: str, min_size: int = 1, max_size: int = 5) -> ConnectionPool:
    return ConnectionPool(
        conninfo,
        min_size=min_size,
        max_size=max_size,
        kwargs={"autocommit": True},
        reset=_reset,
        open=True,
    )
```

- [ ] **Step 4: Implement `backend/app/sql/executor.py`**

```python
"""Run a validated SELECT on the read-only pool and return JSON-safe results."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg import sql as pgsql
from psycopg_pool import ConnectionPool

from app.sql.validator import MAX_ROWS, validate_sql


@dataclass
class SqlResult:
    ok: bool
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    row_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def run_select(pool: ConnectionPool, sql: str, *, max_rows: int = MAX_ROWS,
               timeout: str = "5s") -> SqlResult:
    check = validate_sql(sql, max_rows)
    if not check.ok:
        return SqlResult(ok=False, error=f"Rejected: {check.error}")
    try:
        with pool.connection() as conn, conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute(pgsql.SQL("SET LOCAL statement_timeout = {}").format(pgsql.Literal(timeout)))
            cur = conn.execute(check.sql)
            columns = [d.name for d in cur.description] if cur.description else []
            rows = [[_jsonable(v) for v in row] for row in cur.fetchmany(max_rows)]
    except psycopg.errors.QueryCanceled:
        return SqlResult(ok=False, sql=check.sql,
                         error=f"Query timed out after {timeout}. "
                               "Add filters or aggregate to make it faster.")
    except psycopg.Error as e:
        message = (e.diag.message_primary if e.diag else None) or str(e)
        return SqlResult(ok=False, sql=check.sql, error=f"Database error: {message}")
    return SqlResult(ok=True, sql=check.sql, columns=columns, rows=rows, row_count=len(rows))
```

- [ ] **Step 5: Run the full suite**

Run (in `backend/`): `uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check . ../data
cd ..
git add backend/app/db.py backend/app/sql/executor.py backend/tests/test_executor.py
git commit -m "feat(sql): pooled read-only executor with timeout, row cap and JSON-safe rows"
```

---

### ✅ Milestone 3 checkpoint: SQL safety + end of Plan 1 (human + Claude, no code)

- [ ] **Walkthrough:** what a SQL **parser / AST** is and why parsing beats regex checks; each validator rule and the attack it stops (multiple statements, writes, `SELECT INTO`, `set_config`, catalogs, personal data); why the LIMIT is rewritten; **defence in depth** (validator → read-only role → read-only transaction → timeout → pool reset); connection pooling; why errors go back as text (the agent will use them to self-correct in Plan 2).
- [ ] **Quiz (one at a time):**
  1. Walk me through what happens, layer by layer, when the LLM sends `DELETE FROM orders`.
  2. Why parse SQL with sqlglot instead of checking whether it starts with "SELECT"?
  3. Why is `set_config` dangerous specifically because of connection pooling?
  4. What is a connection pool, and what would happen at 1,000 users without one?
  5. Why does the executor return errors as text instead of raising exceptions?
- [ ] **Append to `DECISIONS.md`:**
```markdown
## SQL safety: defence in depth
1) sqlglot validator: one statement, SELECT/set-operation root, no write/DDL/INTO/locking nodes, no dangerous functions (set_config, pg_sleep…), only five allowed tables, LIMIT ≤ 200. 2) The read-only role (SELECT on five objects). 3) A READ ONLY transaction with SET LOCAL statement_timeout. 4) The pool runs RESET ALL on every returned connection. Any single layer can fail without exposing data.

## Connection pool
psycopg_pool reuses connections instead of opening one per request (faster, and protects Supabase's connection limit).
```
- [ ] **Create `NOTES.md`** with today's summary: what was built (Milestones 1–3), key decisions and why, concepts learned (synthetic data and ground truth, least privilege, embeddings + pgvector, AST validation, defence in depth, pooling), and problems solved during the session.
- [ ] **Commit:** `git add DECISIONS.md NOTES.md && git commit -m "docs: milestone 3 decisions and session notes"`

---

## What comes next (separate plans, written after Plan 1 is done)
- **Plan 2:** agent (LangChain `ChatAnthropic` + `@tool` + LangGraph) + FastAPI API (`/ask`, `/health`, chart hint, rate limit, CORS).
- **Plan 3:** Next.js front end.
- **Plan 4:** evaluation (golden set + runner), Docker image, docker-compose API service, GitHub Actions CI, Render/Vercel/Supabase deployment, README.
