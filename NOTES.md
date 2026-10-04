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
