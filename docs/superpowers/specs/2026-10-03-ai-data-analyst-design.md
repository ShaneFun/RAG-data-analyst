# AI Data Analyst Agent: Design Spec

**Date:** 2026-10-03
**Author:** Fun Siang You (ShaneFun)
**Status:** Approved in design review; written spec awaiting review

---

## 1. Purpose

A portfolio project for **AI Engineer / Applied AI Engineer internship** applications (Ireland and Malaysia), with general software engineering as the fallback role.

The app lets anyone ask business questions in plain English about a fictional online shop, **Larkspur Market**. An AI agent finds the relevant schema knowledge (RAG), writes and runs safe SQL, corrects itself on errors, and returns an answer with the SQL, a results table and a chart.

**Two goals shape every decision:**
1. **Get noticed:** use the stack companies actually use (FastAPI, Next.js, PostgreSQL, pgvector, Claude API, Docker, GitHub Actions), with a live demo link.
2. **Be explainable:** keep the feature set small enough that the author can explain every component and decision in an interview.

### Success criteria
| Criterion | Target |
|---|---|
| Live demo | A public URL (Vercel front end + Render back end) that answers questions |
| Execution accuracy on the golden set (~30 questions) | ≥ 80% (report the real number honestly, whatever it is) |
| Planted trends discovered by the agent | 3 / 3 |
| Correct refusal of unanswerable or harmful questions | All refusal cases in the golden set |
| Safety | No write, DDL or personal-data access possible, enforced by the database role + SQL validator |
| CI | GitHub Actions green on `main` |
| Interview readiness | `README.md` (demo GIF, architecture, results table) + `DECISIONS.md` |

### Non-goals (deliberately out of scope)
- Follow-up questions / conversation memory (a later bonus)
- A LangGraph version of the agent (a later bonus)
- Hybrid (BM25 + vector) knowledge search (a later bonus)
- User accounts, authentication, uploading your own data
- Real customer data of any kind

---

## 2. Architecture

```
┌──────────────┐  POST /ask   ┌──────────────────────────── FastAPI (Docker, Render) ───────────────────────────┐
│ Next.js (TS) │ ───────────► │  rate limit · CORS                                                               │
│ Tailwind     │              │  Agent loop (Claude tool calling, max 8 steps)                                   │
│ Vercel       │ ◄─────────── │     ├─ search_knowledge(query) ──► FastEmbed (bge-small-en-v1.5) ──► pgvector    │
└──────────────┘  JSON answer │     └─ run_sql(sql) ──► sqlglot validator ──► Postgres as read-only role         │
                              └──────────────────────────────────────────────────────────────────────────────────┘
                                                          │
                                         Supabase PostgreSQL + pgvector
                                         (shop tables, safe views, knowledge table)
```

| Layer | Choice |
|---|---|
| Back end | Python 3.12, FastAPI, Pydantic |
| LLM | Claude API with native tool calling; model set by `LLM_MODEL` env var (default `claude-sonnet-5-5`) |
| Embeddings | FastEmbed, `BAAI/bge-small-en-v1.5` (384-d), runs inside the API container |
| Database | Supabase PostgreSQL with the `pgvector` extension |
| SQL safety | `sqlglot` parser + read-only Postgres role + `statement_timeout` |
| Front end | Next.js (App Router) + TypeScript + Tailwind; charts with Recharts |
| Containers | Docker (API image); `docker-compose` for local development (API + `pgvector/pgvector` Postgres) |
| CI | GitHub Actions: ruff, pytest (Postgres service container), front-end build |
| Hosting | API on Render (Docker deploy), web on Vercel, DB on Supabase |

The **agent loop is hand-written** (about 100 lines, no framework), so every step can be explained.

---

## 3. Data

### 3.1 Schema (5 tables)
| Table | Columns |
|---|---|
| `customers` | `id`, `full_name`*, `email`*, `region`, `signup_date`, `signup_channel` |
| `products` | `id`, `name`, `category`, `supplier`, `unit_price` |
| `orders` | `id`, `customer_id`, `order_date`, `channel` (`web`/`app`), `region`, `status` (`completed`/`cancelled`) |
| `order_items` | `id`, `order_id`, `product_id`, `quantity`, `unit_price` |
| `refunds` | `id`, `order_item_id`, `refund_date`, `reason`, `amount` |

\* Fake personal data (generated with Faker), present only so that hiding it can be demonstrated.

### 3.2 Synthetic data generator (`data/generate.py`)
- **Fixed seed (42)** → identical data on every run (reproducibility).
- **Size:** ~2,000 customers, ~120 products, 8 suppliers, 6 categories (Electronics, Home, Fashion, Beauty, Sports, Grocery), 4 regions (North, South, East, West), **~10,000 orders** from 2024-01-01 to 2025-12-31, ~5% of orders cancelled.
- **Baseline:** about 5% of order items are refunded; prices vary by category.

### 3.3 Planted trends (the ground truth)
| ID | Trend | How it's generated | Generator test (must pass) |
|---|---|---|---|
| T1 | **Holiday spike** | Nov and Dec order volume × 1.8 vs. the baseline monthly rate (both years) | Average Nov–Dec monthly orders ≥ 1.5 × average of the other months |
| T2 | **Bad supplier** | Products from supplier `Brightline Goods` refunded at ~15% vs. ~5% baseline | Brightline refund rate ≥ 2.5 × average refund rate of the other suppliers |
| T3 | **March North drop** | In March 2025, North-region Electronics orders cut by ~75% (simulated stock-out); everything else normal | North Electronics orders in Mar 2025 ≤ 40% of the mean of Feb and Apr 2025; other regions' Electronics in Mar 2025 ≥ 80% of their Feb/Apr mean |

T3 is the **star demo**: "Why did North sales drop in March 2025?" needs a drill-down from region → category → month.

### 3.4 Protecting personal data
- View `customers_safe` = `customers` **without** `full_name` and `email`.
- Role `analyst_ro`: `SELECT` only on `customers_safe`, `products`, `orders`, `order_items`, `refunds`. **No access** to `customers` or the knowledge table. `statement_timeout = 5s`.
- The API's SQL connection always uses `analyst_ro`. A separate admin connection (used only by the setup scripts and knowledge search) is never exposed to the LLM.

---

## 4. Knowledge base (RAG over metadata, never data)

Table `knowledge(id, kind, title, content, embedding vector(384))`, with `kind ∈ {dictionary, glossary, example}`. Sources live in YAML under `data/knowledge/` and are loaded by `data/load_knowledge.py`.

| Kind | Content | Count |
|---|---|---|
| `dictionary` | One entry per table (purpose, columns, meaning, **sample values**, e.g. regions = North/South/East/West) | 5 tables |
| `glossary` | Business term → SQL definition | ~10 terms |
| `example` | Verified question → SQL pairs | ~15 |

**Glossary definitions** (fixed):
- **Gross revenue** = Σ `quantity × unit_price` over items in `completed` orders.
- **Net revenue** = gross revenue − Σ `refunds.amount`.
- **AOV** (average order value) = gross revenue ÷ number of completed orders.
- **Refund rate** = refunded order items ÷ order items in completed orders.
- **Active customer** (in a period) = has ≥ 1 completed order in that period.

`search_knowledge(query)` embeds the query and returns the **top 5** by cosine similarity (`title`, `kind`, `content`).

**Separation rule:** none of the golden evaluation questions (Section 8.2) may appear in the `example` set.

---

## 5. Agent

### 5.1 Loop (`backend/app/agent/loop.py`)
1. Build messages: system prompt (role, rules, today's date, the list of allowed tables) + user question.
2. Call Claude with the two tools.
3. If the response contains tool calls → execute them → append the `tool_result` messages → repeat.
4. Stop when Claude returns a final text answer, **or** after **8 tool steps** (then return an honest "couldn't answer" message with what was tried).
5. Return the final payload (Section 6), including every step.

### 5.2 Tools
| Tool | Input | Output |
|---|---|---|
| `search_knowledge` | `query: str` | Top-5 knowledge entries |
| `run_sql` | `sql: str` | `{ok: true, columns, rows (≤200), row_count}` or `{ok: false, error}` |

### 5.3 SQL validator (`backend/app/sql/validator.py`, sqlglot, Postgres dialect)
Rejects unless **all** of the following hold:
- Exactly **one** statement.
- The root is a `SELECT` (CTEs/`WITH` and `UNION` of selects allowed).
- No write, DDL or admin node anywhere (`Insert`, `Update`, `Delete`, `Drop`, `Create`, `Alter`, `Truncate`, `Copy`, `Grant`, `Command`).
- Every referenced table ∈ {`customers_safe`, `products`, `orders`, `order_items`, `refunds`} (CTE names excepted).

On acceptance: if there's no `LIMIT`, or the limit is > 200, set `LIMIT 200`. Then the executor runs it as `analyst_ro`.

### 5.4 Error handling
| Situation | Behaviour |
|---|---|
| SQL execution error | The error text is returned to Claude as the tool result → it may fix and retry (counts as a step) |
| Validator rejection | Not executed; the reason is returned to Claude |
| Timeout (> 5 s) | Cancelled by Postgres; Claude is told to aggregate or filter |
| 0 rows | Returned as-is; the prompt tells Claude to check value spelling via `search_knowledge` or report that no data exists |
| 8 steps reached | Final message: couldn't answer + summary of attempts |
| Off-topic or harmful request | Refuse politely (prompt rule); writes are impossible anyway (role + validator) |
| Claude API error | One retry with backoff → HTTP 503 with a friendly message |

**Principle:** safety lives in **code and database permissions**, not in the prompt.

---

## 6. API

| Endpoint | Description |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `POST /ask` | Body `{"question": str}` (1–500 chars) |

`POST /ask` response:
```json
{
  "answer": "string",
  "sql": ["last successful SQL", "..."],
  "columns": ["..."],
  "rows": [["..."]],
  "chart_hint": {"type": "line | bar | none", "x": "column", "y": "column"},
  "steps": [{"tool": "run_sql", "input": "...", "ok": true, "summary": "12 rows"}],
  "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
  "latency_ms": 0
}
```
- `rows`/`columns` = the result of the **last successful** `run_sql`.
- `chart_hint`: `line` if the first column is a date/month and a numeric column exists; `bar` if the first column is text with ≤ 20 rows and a numeric column exists; otherwise `none`.
- **Rate limit:** 10 requests / hour / IP (slowapi). **CORS:** only the Vercel domain and `http://localhost:3000`.

---

## 7. Front end (single page)
- Question box + example chips, including the star demo "Why did North sales drop in March 2025?".
- Answer card → collapsible SQL → results table → chart (from `chart_hint`) → "How I got this" steps panel.
- Loading state; error banner for 429 (rate limit) and 503.

---

## 8. Testing and evaluation

### 8.1 Automated tests (pytest, CI, no LLM calls)
- **Validator:** allows valid SELECT/CTE/UNION; blocks DROP/INSERT/UPDATE/DELETE, multiple statements, raw `customers`, unknown tables; enforces LIMIT.
- **Generator:** T1–T3 assertions from Section 3.3; row counts in the expected ranges; same seed → identical output.
- **Agent loop with a fake LLM client:** a SQL error leads to a retry; stops at 8 steps; a refusal path; payload shape.
- **Knowledge search** (against a test DB): the query "revenue" returns the glossary revenue entry in the top 5.
- **API:** `/health`, input validation, rate-limit response.

### 8.2 Evaluation (`eval/run_eval.py`, run by hand; uses the real Claude API)
- `eval/questions.yaml`: ~30 items `{id, question, gold_sql | expect_refusal, tags}`, covering simple lookups, JOINs, aggregations, time series, T1–T3 discovery questions, and ~3 refusals.
- **Metrics:**
  - **execution accuracy:** result set equals the gold SQL result, comparing rows order-insensitively with numbers rounded to 2 dp
  - **valid-SQL rate**
  - **retrieval recall@5:** expected tables appear in the knowledge results
  - **trends found X/3**
  - **refusal accuracy**
  - **average steps, latency and cost per question**
- Output: `eval/results/<YYYY-MM-DD>.json` + a markdown summary that is copied into the README.

### 8.3 CI (`.github/workflows/ci.yml`, on push / pull request)
`ruff check` → pytest (with a `pgvector/pgvector` service container) → `npm ci && npm run lint && npm run build` in `frontend/`.

---

## 9. Deployment
| Part | Where | Setup |
|---|---|---|
| DB | Supabase | Run `data/schema.sql`, `data/generate.py`, `data/roles.sql`, `data/load_knowledge.py` |
| API | Render (Docker) | Env: `DATABASE_URL_RO` (analyst_ro), `DATABASE_URL_ADMIN`, `ANTHROPIC_API_KEY`, `LLM_MODEL`, `ALLOWED_ORIGINS` |
| Web | Vercel | Env: `NEXT_PUBLIC_API_URL` |
| Local | `docker compose up` | API + Postgres (pgvector image); `.env.example` documents every variable |

**Cost guard:** set a monthly spend limit in the Anthropic console, plus the per-IP rate limit.

---

## 10. Repository layout
```
ai-data-analyst/
├─ backend/
│  ├─ app/
│  │  ├─ main.py            # FastAPI app, routes, CORS, rate limit
│  │  ├─ config.py          # settings from env
│  │  ├─ schemas.py         # request/response models
│  │  ├─ agent/  (loop.py, tools.py, prompts.py, llm.py)
│  │  ├─ sql/    (validator.py, executor.py)
│  │  └─ knowledge/ (embed.py, search.py)
│  ├─ tests/
│  ├─ Dockerfile
│  └─ pyproject.toml
├─ data/  (schema.sql, roles.sql, generate.py, load_knowledge.py, knowledge/*.yaml)
├─ eval/  (questions.yaml, run_eval.py, results/)
├─ frontend/  (Next.js app)
├─ docker-compose.yml
├─ .github/workflows/ci.yml
├─ .env.example
├─ README.md
├─ DECISIONS.md
└─ docs/superpowers/specs/
```

---

## 11. Build milestones (each ends with an explain-back check)
1. **Data:** schema, generator with T1–T3, roles/views, generator tests.
2. **Knowledge:** YAML sources, embeddings, pgvector search, search test.
3. **SQL safety:** validator + executor + tests.
4. **Agent:** LLM client, tools, loop, fake-LLM tests.
5. **API:** FastAPI routes, schemas, chart hint, rate limit, CORS.
6. **Front end:** single page with answer/SQL/table/chart/steps.
7. **Evaluation:** golden set + runner + first results.
8. **Ship:** Docker, docker-compose, CI, Render/Vercel/Supabase deploy, README, DECISIONS.md.

After each milestone the author explains in their own words what was built and why, and records any decision in `DECISIONS.md`.

## 12. Later bonuses (not part of this spec)
Follow-up questions (conversation memory) · LangGraph version of the loop · hybrid BM25 + vector knowledge search with RRF · Phoenix/OpenTelemetry tracing.
