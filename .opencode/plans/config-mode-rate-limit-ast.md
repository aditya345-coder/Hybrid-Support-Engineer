# Implementation Plan: Config System, Ingestion Mode, Rate Limiter Fix, File Limit, AST Integration

**Status:** Planned
**Applies to:** Hybrid Support Agent

---

## Overview

1. **Centralized config system** (`src/settings.py`)
2. **LOCAL_MODE** env var — clone vs GitHub API
3. **Rate limiter** — use Auth0 `sub` instead of `session_id`
4. **500 file limit** enforcement
5. **AST code indexer** integration into Qdrant
6. **AST call graph** — skip for now (add to features-to-skip.md)

---

## 1. Centralized Config (`src/settings.py`)

New `src/settings.py` with `Settings` class reading env vars:

- `LOCAL_MODE` (bool, default False)
- `REPO_FILE_LIMIT` (int, default 500)
- `RATE_LIMIT_MAX` (int, default 50)
- `MAX_ISSUES_FETCHED` (int, default 20)
- `MAX_VERIFY_RETRIES` (int, default 3)
- `DOCS_UPSERT_BATCH` (int, default 64)
- `AST_ENABLED` (bool, default True)
- `AST_EXCLUDE_DIRS` (list, default `tests,examples,docs,node_modules,__pycache__,.git`)
- All existing env vars for Qdrant, Neo4j, Auth0, LLM, GitHub, Paths

Then replace `os.getenv()` calls across 6+ files.

---

## 2. LOCAL_MODE: Clone vs API

**LOCAL_MODE=T** (existing behavior): clone with GitPython, walk filesystem.

**LOCAL_MODE=F** (default, new): Use PyGithub API to fetch `.md` files:
- `fetch_via_api()` → `repo.get_contents("docs")` recursive walk
- Falls back to `documentation/` then root `README.md` + `.md` files
- Process in memory, same MarkdownHeaderTextSplitter + Qdrant upload
- No incremental sync — full re-fetch each time (<500 files, acceptable)

---

## 3. Rate Limiter: Auth0 `sub`

Change `solve_ticket` in `src/main.py`:
- Inject `user: dict = Depends(get_current_user)` as parameter
- Pass `user.get("sub", "anonymous")` to `check_rate_limit` instead of `session_id`
- Auth bypass still works (returns `{"sub": "anonymous"}` when Auth0 unset)

---

## 4. 500 File Limit

In `docs_loader.py:load_and_split()`, after collecting files:
```python
if len(files_to_process) > settings.REPO_FILE_LIMIT:
    raise ValueError(f"Repo has {len(files_to_process)} files, exceeds {settings.REPO_FILE_LIMIT}")
```

---

## 5. AST Code Indexer

### Ingestion (LOCAL_MODE=T only initially)
- Add `index_directory(directory, exclude_dirs)` to `code_indexer.py`
- New phase `indexing_code` (10% weight) in `_prepare_repo_task`
- Embed docstrings/signatures with FastEmbed (384-dim)
- Store in Qdrant `code_{session_id}` collection
- Payload: symbol_name, symbol_type, signature, file_path, line_start, line_end, source_code

### Retrieval
- `vector_store.py`: add `search_code()` for code collection
- `hybrid_retriever.py`: include code results
- `support_agent.py`: include code context in generation prompt

---

## 6. AST Call Graph — Deferred

Skip `callers`/`callees` fields. Add to `04-features-to-skip.md`:
- Why: storage overhead, cross-file resolution complexity, marginal benefit
- Reconsider when: users request call-chain queries

---

## Files Changed Summary

| File | Change |
|------|--------|
| `src/settings.py` | **New** — central config |
| `.env.example` | Add LOCAL_MODE, AST_ENABLED, AST_EXCLUDE_DIRS |
| `src/ingestion/docs_loader.py` | Add fetch_via_api(), 500 limit, conditional path |
| `src/ingestion/github_loader.py` | Use settings.MAX_ISSUES_FETCHED |
| `src/ingestion/code_indexer.py` | Add index_directory() with exclude |
| `src/main.py` | Inject user in solve_ticket, add AST phase |
| `src/middleware/rate_limit.py` | Use settings.RATE_LIMIT_MAX |
| `src/database/vector_store.py` | Add search_code() |
| `src/database/hybrid_retriever.py` | Include code results |
| `src/agents/support_agent.py` | Use settings, include code context |
| `04-features-to-skip.md` | Add AST call graph section |

---

## Implementation Order

1. Create `src/settings.py` + wire into all files
2. Add 500 file limit guard
3. Fix rate limiter user identity
4. Add LOCAL_MODE + API fetch
5. Update features-to-skip.md
6. AST code indexing integration
