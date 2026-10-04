# Design decisions

My interview script: what I chose, why, and what I'd change at scale.

## Data

### Synthetic data with planted trends
Real shop data is private, and with real data I could never know the correct answer. So I generate a fictional shop (Larkspur Market: 2,000 customers, 120 products, ~10,000 orders over 2024–2025) with a **fixed seed (42)** for reproducibility: tests are deterministic and evaluation scores are comparable across runs. I **injected three known patterns as ground truth**: a Nov–Dec holiday spike, one supplier (Brightline Goods) with ~3x the refund rate, and a March 2025 stock-out that removes most North-region Electronics sales. Tests prove they exist; the evaluation measures whether the agent discovers them.

### Bulk loading with COPY
COPY streams all ~35k rows instead of one INSERT round trip per row, inside one transaction (all-or-nothing), loading parent tables before children to satisfy foreign keys.

### Indexes
B-tree indexes on the columns used for filtering and joining (dates, region, foreign keys, category, supplier). The workload is read-heavy (load once, query constantly), so slower writes and extra storage are an acceptable trade-off.

### Separate test database
Tests drop and rebuild the schema every run so they start from a known state. They use `larkspur_test`, isolated from the dev database `larkspur`, so tests never destroy data I'm working with and can run while the app runs.

## Security

### Least privilege + data minimisation
Agent SQL runs as `analyst_ro`: SELECT on exactly five objects. Personal data (names, emails) lives only in `customers`, which the role cannot read. It reads the `customers_safe` view instead (region, signup date, channel), so it can still answer customer analytics questions without ever seeing who the customers are.

### Defence in depth (four independent layers)
1. **sqlglot validator**: parses the SQL into an AST; only a single SELECT/set-operation over allowed tables; no write/DDL/INTO/locking nodes; no dangerous functions (set_config, pg_sleep, file access); LIMIT ≤ 200.
2. **READ ONLY transaction** with `SET LOCAL statement_timeout`.
3. **Role defaults**: `default_transaction_read_only = on`, `statement_timeout = 5s`.
4. **Permissions**: SELECT only.

The prompt is not a security boundary: prompt injection can fool the LLM, but it cannot change database permissions. The timeout protects **availability**: even a read-only query (e.g. an accidental cross join) could otherwise slow the database for every user.

### Parse, don't string-match
`SELECT 1; DROP TABLE orders` and `SELECT … INTO` both start with SELECT; string checks would let them through and would wrongly block valid CTEs. The parser sees the real structure.

### Connection pool with reset
psycopg_pool reuses connections (faster, protects the database's connection limit) and runs `RESET ALL` when a connection is returned, so no session setting leaks between requests.

### Errors as text
The executor returns errors as structured text instead of raising, so the agent can read them and self-correct (with a step limit).

## RAG

### Retrieve metadata, never data
The knowledge base holds 29 entries: a data dictionary (5 tables, with real values like region names), a business glossary (9 definitions, e.g. gross revenue = SUM(quantity × unit_price) on completed orders) and 15 verified question→SQL examples. Analytics answers need **aggregation** over thousands of rows, which similarity search cannot do, so RAG teaches the LLM how to write the query and **SQL computes the exact answer**. Every example query is tested against the database as the read-only role, so the agent is never taught broken SQL. Examples deliberately avoid the planted trends (no data leakage into the evaluation).

### Embeddings and search
BAAI/bge-small-en-v1.5 via FastEmbed (384-d, runs locally, no API cost). Queries and passages are embedded differently (BGE's query instruction). Cosine similarity in pgvector, top 5: search only needs good recall, and the LLM picks the relevant entries. Next improvements: hybrid search (BM25 + vectors, RRF), a cross-encoder re-ranker, synonyms in entries.

### pgvector instead of a dedicated vector database
29 vectors fit easily in the same Postgres as the data: no extra service, cost or sync problems. An exact scan takes about a millisecond, so no vector index is needed. I'd revisit at millions of vectors.
