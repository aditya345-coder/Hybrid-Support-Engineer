# Ingestion Pipeline Optimization — Implementation Plan 5

## Goal

Reduce total ingestion time from ~3-5 min to ~60-90s by optimizing the 5-phase `_prepare_repo_task` pipeline in `src/main.py`.

---

## Phase 1: Quick Wins (Estimated: 60-70% faster)

### Task 1: Batch LLM calls in `GitHubGraphLoader`

**File:** `src/ingestion/github_loader.py`

**Problem:** `run()` calls `extract_graph_data()` once per issue — 20 LLM calls, each taking 2-10s.

**Solution:** Collect up to 10 issue bodies, send one prompt asking the LLM to extract graph data for all of them as a JSON array.

**Changes:**
1. `run()` — Instead of processing issues one at a time, batch them into groups of 5-10
2. New method `extract_graph_data_batch()` — sends a batch prompt

**Expected gain:** 20 LLM calls → 2-4 calls, saves ~80s.

---

### Task 2: Shallow clone + repo caching

**File:** `src/ingestion/docs_loader.py` — `prepare_local_repo()`

**Problem:** `Repo.clone_from()` clones full history (unnecessary for docs extraction).

**Solution:** Add `depth=1` to clone. Add a simple cache policy: if the local repo exists and was cloned within the last hour, skip the fetch too.

**Expected gain:** Clone time from 30-60s → ~5s.

---

### Task 3: Reduce default `MAX_ISSUES_FETCHED`

**File:** `src/settings.py` line 19

**Change:** `"20"` → `"10"`

**Expected gain:** Half the LLM work (compounds with Task 1).

---

### Task 4: Parallel docs indexing + graph building

**File:** `src/main.py` — `_prepare_repo_task()`

**Problem:** Phases 3 (indexing_docs), 4 (indexing_code), and 5 (building_graph) run sequentially but are independent.

**Solution:** Use `ThreadPoolExecutor(max_workers=3)` to run them concurrently after `parsing_docs` completes. Extract `gh_loader.run()` and code-indexing into standalone functions for `pool.submit()`.

**Progress reporting:** Report per-phase progress independently during parallel execution. After both complete, jump to combined percentage.

**Expected gain:** Shaves ~30-40% off total wall time.

---

## Phase 2: Embedding Optimization (Estimated: 15-20% faster)

### Task 5: Batch feature embedding matching

**File:** `src/ingestion/docs_loader.py`

**Problem:** `_best_matching_feature()` calls `embed_query(text)` per chunk (O(n × m)). With ~100 chunks × 10 features = 100 calls at ~150ms each = ~150s.

**Solution:** After parsing all chunks, call `embed_documents()` once on all texts, compute vectorized cosine similarity against feature embeddings using numpy.

**Expected gain:** Reduces ~100+ embedding calls to 1 batch call, saves ~150s.

---

## Files to Modify

| File | Tasks | Est. Lines |
|------|-------|-----------|
| `src/settings.py` | Task 3 | 1 |
| `src/ingestion/github_loader.py` | Task 1 | ~40 |
| `src/ingestion/docs_loader.py` | Task 2, 5 | ~50 |
| `src/main.py` | Task 4 | ~50 |

## New Tests Needed

1. **Batch LLM parsing** — mock LLM returns multi-issue JSON array
2. **Batch embedding** — batch matching produces same results as per-chunk
3. **Parallel phases** — concurrent futures complete and errors propagate

## Rollout Order

1. Task 3 (settings) — trivially safe
2. Task 2 (shallow clone) — no behavioral change
3. Task 1 (batch LLM) — reduces API calls, same output
4. Task 5 (batch embedding) — reduces embedding calls, same results
5. Task 4 (parallel phases) — biggest structural change, do last

## Expected Results

| Metric | Before | After |
|--------|--------|-------|
| Total time | ~3-5 min | ~60-90s |
| LLM calls | 20 | 2-4 |
| Clone time | 30-60s | ~5s |
| Feature matching | ~150s | ~5s |
| Phases | serial | parallel |
