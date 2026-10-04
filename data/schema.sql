CREATE EXTENSION IF NOT EXISTS vector;          -- turn on pgvector (adds the "vector" column type)

-- Customers. full_name + email are PERSONAL DATA: the AI will never be allowed to read them.
CREATE TABLE customers (
    id             integer PRIMARY KEY,
    full_name      text    NOT NULL,
    email          text    NOT NULL UNIQUE,
    region         text    NOT NULL,                       -- North / South / East / West
    signup_date    date    NOT NULL,
    signup_channel text    NOT NULL CHECK (signup_channel IN ('web', 'app'))
);

CREATE TABLE products (
    id         integer       PRIMARY KEY,
    name       text          NOT NULL,
    category   text          NOT NULL,                     -- Electronics, Home, Fashion...
    supplier   text          NOT NULL,
    unit_price numeric(10,2) NOT NULL                      -- numeric = exact money (no float rounding errors)
);

-- One row per checkout.
CREATE TABLE orders (
    id          integer PRIMARY KEY,
    customer_id integer NOT NULL REFERENCES customers(id), -- foreign key: must be a real customer
    order_date  date    NOT NULL,
    channel     text    NOT NULL CHECK (channel IN ('web', 'app')),
    region      text    NOT NULL,
    status      text    NOT NULL CHECK (status IN ('completed', 'cancelled'))
);

-- One row per product line inside an order.
CREATE TABLE order_items (
    id         integer       PRIMARY KEY,
    order_id   integer       NOT NULL REFERENCES orders(id),
    product_id integer       NOT NULL REFERENCES products(id),
    quantity   integer       NOT NULL CHECK (quantity > 0),
    unit_price numeric(10,2) NOT NULL                      -- price paid at the time of the order
);

CREATE TABLE refunds (
    id            integer       PRIMARY KEY,
    order_item_id integer       NOT NULL UNIQUE REFERENCES order_items(id),  -- an item is refunded at most once
    refund_date   date          NOT NULL,
    reason        text          NOT NULL,
    amount        numeric(10,2) NOT NULL
);

-- Parent sections of the long handbook document (returned to the LLM in full, never embedded).
CREATE TABLE knowledge_sections (
    id      serial PRIMARY KEY,
    title   text   NOT NULL UNIQUE,
    content text   NOT NULL
);

-- RAG knowledge base: descriptions of the data (NOT the data itself) + their embeddings.
-- Handbook rows are small child chunks pointing to their parent section (parent-child retrieval).
CREATE TABLE knowledge (
    id         serial PRIMARY KEY,
    kind       text   NOT NULL CHECK (kind IN ('dictionary', 'glossary', 'example', 'handbook')),
    title      text   NOT NULL,
    content    text   NOT NULL,
    section_id integer REFERENCES knowledge_sections(id),  -- only for kind = 'handbook'
    embedding  vector(384) NOT NULL                        -- 384 numbers from the bge-small model
);

-- Indexes on the columns the agent filters and joins on.
CREATE INDEX idx_orders_order_date       ON orders (order_date);
CREATE INDEX idx_orders_region           ON orders (region);
CREATE INDEX idx_orders_customer_id      ON orders (customer_id);
CREATE INDEX idx_order_items_order_id    ON order_items (order_id);
CREATE INDEX idx_order_items_product_id  ON order_items (product_id);
CREATE INDEX idx_products_category       ON products (category);
CREATE INDEX idx_products_supplier       ON products (supplier);
-- refunds.order_item_id is already indexed by its UNIQUE constraint.