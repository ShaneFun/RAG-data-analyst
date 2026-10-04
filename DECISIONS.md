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

### A long handbook, so chunking has a real job
Real teams keep wiki pages next to their database. I added a ~2,000-word data handbook (business rules, refund policy, privacy, common query mistakes), written to match the generator and with a test that it never hints at the planted trends, so the evaluation stays honest.
- **Header-based chunking** (LangChain `MarkdownHeaderTextSplitter`): one chunk per `###` subsection, 20 chunks. Each chunk's embedded text starts with its heading path ("Refunds > Refund policy") so it keeps its context. The curated entries are not chunked: each is already one self-contained topic.
- **Parent-child retrieval**: small chunks match precisely; the LLM receives the whole `##` section (stored in `knowledge_sections`, not embedded) and results are de-duplicated by parent. Search small, read big.

### Hybrid search with RRF
Vector search understands meaning ("basket size" ≈ AOV); BM25 matches exact tokens (AOV, Brightline, COUNT DISTINCT). Each returns 20 candidates; **Reciprocal Rank Fusion** (score = Σ 1/(60 + rank)) merges them using ranks only, so the incompatible cosine and BM25 scores never need normalising. With ~50 entries, BM25 is rebuilt per query in Python (microseconds); at scale I'd move it into Postgres (full-text search or ParadeDB `pg_search`). An optional `kind` filter (metadata filtering) lets the agent search only examples, definitions or the handbook.

### Measure retrieval separately
A free retrieval eval (25 queries with known correct entries) compares the three modes: recall@5 is 100% for all, hit@1 88% → 92% and MRR 0.923 → 0.953 with hybrid. The honest conclusion: on a small knowledge base vector search already finds the right entries; hybrid mainly improves ranking, and it guards against exact-term misses as the knowledge base grows. No re-ranker: with top 5 of ~50 short entries it would add latency for no measurable gain.

### Not added on purpose
Separate query routing and rewriting: the agent already chooses its tool and writes its own search queries. GraphRAG: the data is relational, so foreign keys are the edges and SQL joins are the traversals.

## Agent

### LangGraph state graph with LangChain components
The agent is a small LangGraph graph: `agent` (the LLM with two tools bound) → `tools` → back to `agent`, ending when the LLM answers or after **8 tool calls**. LangChain provides the model wrapper and the `@tool` definitions; LangGraph makes the loop, the stop condition and the state explicit and testable. I deliberately did **not** use LangChain's prebuilt SQL agent: it would run SQL its own way and bypass my validator and read-only role.

### Two tools only
`search_knowledge(query)` (RAG over the knowledge base) and `run_sql(sql)` (validated, read-only, ≤200 rows). Both return **text for the LLM and a structured artifact for the API** (`response_format="content_and_artifact"`): the LLM sees at most 50 rows (keeps prompts small), while the website gets up to 200 rows plus the SQL. Tool crashes and unknown tools become error messages instead of crashing the request.

### Self-correction
Database errors come back to the LLM as the tool result, so it reads e.g. "column category does not exist" and rewrites the query (execution-guided correction). The step limit stops endless loops. When it is hit, the agent gets **one last call with tools disabled** (`tool_choice="none"`) and must answer from what it already found and say what it couldn't check. I added this after a real run: on "Why did North sales drop?" the agent had found the Electronics stock-out by step 8 but returned "couldn't finish", throwing the evidence away.

### DeepSeek as the LLM
`deepseek-chat` through LangChain's `ChatDeepSeek`: strong at SQL and tool calling, and very cheap (the whole evaluation costs cents). Temperature 0 for deterministic SQL, one automatic retry, 60 s timeout. Because the model is behind LangChain's chat-model interface, swapping providers is a one-file change (`app/agent/llm.py`).

### Prompt design
The system prompt lists the tools, the five readable tables, today's date and a short procedure: search knowledge first, aggregate in SQL, fix errors, break "why" questions down by dimension, only state numbers from query results, and decline off-topic, destructive or personal-data requests. Security still never depends on the prompt.

### Testing without paying for API calls
Graph tests use a scripted fake chat model, so the loop, self-correction, step limit and refusals are tested deterministically and for free. Real-model quality is measured separately by the evaluation (Day 3).

## API

### FastAPI
`POST /ask` and `GET /health`, with Pydantic request/response models (question 1–500 characters, whitespace stripped). The endpoint is a plain `def`, so FastAPI runs the blocking agent in its thread pool. `create_app(settings, ask)` takes the agent as a dependency, so API tests use a fake.

### Protecting the public demo
Per-IP rate limit (slowapi, 10 questions/hour by default), CORS restricted to the website's origin, DeepSeek outages mapped to HTTP 503 with a friendly message, and the server refuses to start without an API key. Plus a spend limit on the DeepSeek account.

## Evaluation

### Execution accuracy, not SQL matching
30 held-out questions (none appear in the knowledge base): 23 with a gold SQL query, 4 trend-discovery questions and 3 that must be declined. Many different SQL queries are correct, so I compare **results**: the gold query and the agent's last query both run, and the agent passes if every gold column appears among its columns (order-insensitive, extra columns allowed, numbers within 0.5%). Trend questions are scored by whether the answer names the planted cause (e.g. "Electronics", "Brightline"), refusals by declining without running SQL. A test runs every gold query as the read-only role, so the benchmark itself can't be wrong.

### Why a fixed eval set matters
It turns "the demo looked good" into a number I can re-run after every prompt or model change (regression testing for LLM behaviour), with cost and latency recorded per question.

## Deployment

### One Docker image, three free services
The API runs as a Docker image (python:3.12-slim + uv, locked dependencies, embedding model baked in so cold starts don't download 70 MB, non-root user). Render builds it from `render.yaml`; Postgres + pgvector is on Supabase (the same `data.setup_db` script builds it); the Next.js site is on Vercel. Secrets live only in the platforms' dashboards (`sync: false`), never in git. `--proxy-headers` lets the rate limiter see real client IPs behind Render's proxy.

### Streaming
`POST /ask/stream` returns Server-Sent Events from LangGraph's stream modes: `updates` gives a `step` event after each tool call, `messages` gives the LLM's tokens, and `values` keeps the full state for the final `result` event (identical to `/ask`). Text the model writes before a tool call is thinking out loud, so the client clears its draft on every step. Errors after the response has started can't change the HTTP status, so they become an `error` event. Both endpoints share one rate-limit budget. Plain `fetch` + a stream reader instead of `EventSource`, because `EventSource` only supports GET.

### CI
GitHub Actions runs on every push: ruff + 160+ pytest tests against a real pgvector service container (no LLM key needed because agent tests use a fake), frontend lint + production build, and a Docker build. The paid LLM eval runs manually, not in CI.

## Frontend

### Show the work, not just the answer
Next.js (App Router) + Tailwind + recharts. The answer sits next to its evidence: a chart picked by the backend's `chart_hint`, the result table, the exact SQL, and a numbered **step trace** where failed queries are marked, so a user can see the agent search, fail, fix and answer. For an analytics tool, trust comes from being able to check the numbers.
