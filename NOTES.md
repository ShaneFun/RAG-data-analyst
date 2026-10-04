# Session notes

## Day 1 — back-end foundation (2026-10-04)

### What we built (103 tests passing)
| Step | Built | Key files |
|---|---|---|
| ① | Postgres 16 + pgvector in Docker | `docker-compose.yml` |
| ② | Python 3.12 project with uv, settings, smoke tests | `backend/pyproject.toml`, `app/config.py` |
| ③ | 5 shop tables + knowledge table + 7 indexes | `data/schema.sql`, `data/db_setup.py` |
| ④ | Synthetic data generator with 3 planted trends | `data/generate.py` |
| ⑤ | COPY loader, read-only role, `customers_safe` view, setup command | `data/load_data.py`, `data/roles.py`, `data/setup_db.py` |
| ⑥ | Knowledge base: 5 table descriptions, 9 glossary terms, 15 example queries | `data/knowledge/*.yaml`, `data/knowledge_entries.py` |
| ⑦ | Embeddings + pgvector semantic search | `app/knowledge/embed.py`, `search.py`, `data/load_knowledge.py` |
| ⑧ | SQL validator + pooled read-only executor | `app/sql/validator.py`, `executor.py`, `app/db.py` |

Rebuild the dev database any time: `uv run --project backend python -m data.setup_db`
Run tests: `cd backend` then `uv run pytest -v`

### Concepts learned
- **Docker / docker-compose**: a container runs Postgres locally; a volume keeps its data; the same image runs in CI. Docker doesn't upload anything — deploying to Supabase (Day 3) rebuilds the data with the same setup script.
- **uv**: installs Python, creates `.venv`, locks exact versions in `uv.lock` (reproducible installs).
- **TDD**: write the test first, watch it fail, then write the code.
- **Synthetic data, fixed seed, ground truth**; **COPY** bulk loading; **foreign keys** and load order; **indexes** (faster reads, slower writes).
- **CIA triad**: Confidentiality (privacy view, permissions), Integrity (read-only), Availability (timeout).
- **Least privilege, data minimisation, defence in depth**; the prompt is not a security boundary.
- **RAG over metadata, not data**: SQL does the maths.
- **Semantic search**: embeddings = a map of meaning; cosine similarity; top-k + the LLM chooses; improve with hybrid search and re-ranking.
- **Parsing (AST) beats string matching** for SQL safety.
- **Connection pooling**; errors as text for **self-correction**.

### Problems solved
- Docker said "virtualization not detected" → the real cause was missing **WSL 2** (`wsl --install --no-distribution`, then restart).
- `no configuration file provided` → the file was named `docker.compose.yml` instead of `docker-compose.yml`.
- `empty compose file` → files were pasted but **not saved** (watch for the ● on the tab; turn on Auto Save).
- Only 2 tests collected → `test_schema.py` was in `data/` instead of `backend/tests/` (pytest only looks in `testpaths`).
- Ruff lint: import order (marked `app`, `data`, `tests` as first-party), merged nested `with` blocks, wrapped implicitly concatenated strings in brackets (prevents missing-comma bugs).

### Quiz takeaways to revise
Defence in depth & availability · `customers_safe` = data minimisation · test DB isolation · what RAG retrieves and why not rows · how semantic search works · top-5 + LLM chooses · prompt-injection walkthrough · parse vs string check · errors for self-correction.

### Next: Day 2
Get an **Anthropic API key** (console.anthropic.com) and set a small monthly spend limit. Then: Claude + tools → LangGraph agent → FastAPI `/ask`.

## Day 2 — the agent + API (2026-10-04)

### What we built (130 tests passing)
| Step | Built | Key files |
|---|---|---|
| ⑨ | DeepSeek chat model, the two tools, system prompt | `app/agent/llm.py`, `tools.py`, `prompts.py` |
| ⑩ | LangGraph agent loop: self-correction, 8-step limit, step log, token/cost tracking, chart hints | `app/agent/graph.py`, `service.py`, `app/charts.py` |
| ⑫–⑬ | FastAPI `/ask` + `/health`, Pydantic schemas, rate limit, CORS, 503 on LLM outage, CLI | `app/main.py`, `schemas.py`, `wiring.py`, `cli.py` |

### Try the real agent (needs your DeepSeek key)
1. Copy `backend/.env.example` to `backend/.env` and set `DEEPSEEK_API_KEY=...` (never commit `.env`).
2. From `backend/`: `uv run python -m app.cli "Why did North sales drop in March 2025?"`
3. Or start the API: `uv run uvicorn app.main:app --reload`, then open http://localhost:8000/docs and try `POST /ask`.

### Concepts learned
- **Agent vs pipeline**: the LLM decides which tool to call next, in a loop, until it can answer.
- **Tool calling**: the model returns `tool_calls`; our code runs them and sends `ToolMessage`s back. The model never executes anything.
- **LangGraph**: state (messages, step count, log), nodes (agent, tools), a conditional edge (more tools or END).
- **Content + artifact tools**: short text for the LLM, full data for the API.
- **Self-correction** via error feedback; **step limits** to stop loops.
- **Fakes for testing LLM code**: scripted responses make agent tests free and deterministic.
- **FastAPI + Pydantic** validation, dependency injection via `create_app(ask=...)`, **rate limiting**, **CORS**, mapping upstream failures to **503**.

## Day 3: frontend, evaluation, shipping (2026-10-04)

### What we built
| Built | Key files |
|---|---|
| Next.js site: question box, example questions, answer, chart, table, SQL, step trace | `frontend/components/*`, `frontend/lib/api.ts` |
| 30-question evaluation with execution-accuracy scoring: **30/30**, $0.04 per run | `backend/evals/*` |
| Forced final answer at the tool limit | `app/agent/graph.py` |
| Dockerfile (model baked in, non-root), compose `api` service | `backend/Dockerfile`, `docker-compose.yml` |
| CI (backend, frontend, Docker), Render blueprint, deploy guide | `.github/workflows/ci.yml`, `render.yaml`, `README.md` |

### Problems solved (good interview stories)
- **Agent gave up with the answer in hand**: a "why" question used all 8 tool calls and returned "couldn't finish" even though step 8 had found the cause. Fix: at the limit, one more LLM call with `tool_choice="none"` that must answer from the evidence.
- **The eval was wrong, not the agent**: first run 24/30. All 6 failures were correct answers in a different shape (top 5 vs top 1, 40.07% vs 0.4007, "2025-03" vs a date). Lesson: read failures before trusting a metric. I made scoring lenient on presentation and strict on content, with a test per case.
- **Running the tests broke the app**: Postgres roles are server-wide, so the test fixture changed `analyst_ro`'s password for the dev database too. Fix: tests use the same password from settings.
- **Windows console crash** on the → character: `sys.stdout.reconfigure(encoding="utf-8")`.

### Concepts learned
- **Execution accuracy** vs exact-match SQL; **false negatives** in evaluation; **eval as a regression test** for prompts/models.
- **Graceful degradation**: an agent should return its best partial answer, not nothing.
- **Docker layer caching** (dependencies before code), baking models into images, non-root containers, `--proxy-headers` behind a load balancer.
- **CI service containers** (a real Postgres in GitHub Actions); secrets only in platform dashboards.
