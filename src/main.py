import hashlib
import hmac
import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import Depends, FastAPI, HTTPException, Header, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Callable, cast

from ingestion.docs_loader import DocsLoader
from ingestion.github_loader import GitHubGraphLoader

from config import RAW_DOCS_DIR

from agents.support_agent import SupportAgent
from middleware.rate_limit import check_rate_limit, decrement_rate_limit
from middleware.feedback import FeedbackStore
from middleware.auth import get_current_user
from middleware.webhook_handler import handle_push, handle_issue_event, handle_pr_event
from utils.logging_config import setup_logging
from utils.validators import validate_session_id
from settings import settings

logger = setup_logging(__name__)
app = FastAPI(title="Hybrid Support Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_feedback_store = FeedbackStore()

# In-memory ingestion status store.
# For real SaaS, this should be persisted (e.g., Redis) and scoped per deployment.
_SESSION_STATUS: dict[str, dict[str, Any]] = {}

logger.info("Initializing SupportAgent...")
agent: Any = SupportAgent()
logger.info("SupportAgent initialized successfully.")

# Startup security check
env = os.getenv("ENV", "development").lower()
if env == "production" and not settings.AUTH_ENABLED:
    logger.critical(
        "AUTH_ENABLED is False in production — this is a security risk"
    )


class QueryRequest(BaseModel):
    user_query: str
    # Optional session isolation key; can also be provided via `X-Session-Id` header.
    session_id: str | None = None
    # Optional flags/plumbing for future roadmap items.
    allow_web_search: bool = False
    repo_url: str | None = None
    github_token: str | None = None


class PrepareRepoRequest(BaseModel):
    repo_url: str
    github_token: str | None = None
    session_id: str


class FeedbackRequest(BaseModel):
    query: str
    answer: str
    feature_detected: str = "General"
    thumbs_up: bool
    session_id: str


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    raw_body = await request.body()
    
    if not settings.WEBHOOK_SECRET:
        env = os.getenv("ENV", "development").lower()
        if env == "production":
            logger.critical("WEBHOOK_SECRET not configured in production - refusing webhook")
            return JSONResponse(status_code=503, content={"detail": "Webhook authentication not configured"})
        elif os.getenv("WEBHOOK_AUTH_DISABLED", "false").lower() != "true":
            logger.warning("WEBHOOK_SECRET not configured - webhook authentication disabled")
            return JSONResponse(status_code=503, content={"detail": "Webhook authentication not configured"})
        else:
            logger.warning("WEBHOOK_SECRET not configured - authentication explicitly disabled via WEBHOOK_AUTH_DISABLED")
    else:
        signature_header = request.headers.get("X-Hub-Signature-256", "")
        if not signature_header:
            logger.warning("Webhook missing signature header")
            raise HTTPException(status_code=403, detail="Missing signature")
        
        expected_signature = "sha256=" + hmac.new(
            settings.WEBHOOK_SECRET.encode(),
            raw_body,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(expected_signature, signature_header):
            logger.warning("Webhook signature verification failed")
            raise HTTPException(status_code=403, detail="Invalid signature")
    
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    event = request.headers.get("X-GitHub-Event", "")
    session_id = settings.WEBHOOK_SESSION_ID or ""

    logger.info("Webhook received", extra={"event": event, "session_id": session_id})

    if event == "push":
        background_tasks.add_task(handle_push, payload, session_id)
    elif event == "issues":
        background_tasks.add_task(handle_issue_event, payload, session_id)
    elif event == "pull_request":
        background_tasks.add_task(handle_pr_event, payload, session_id)
    else:
        logger.info("Unhandled webhook event", extra={"event": event})

    return {"status": "ok"}


@app.post("/v1/solve-ticket", dependencies=[Depends(get_current_user)])
async def solve_ticket(
    request: QueryRequest,
    user: dict = Depends(get_current_user),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    try:
        # Running our LangGraph State Machine
        logger.info("Solving ticket", extra={"query": request.user_query})
        session_id = x_session_id or request.session_id
        if session_id:
            session_id = validate_session_id(session_id)
            if not session_id:
                raise HTTPException(status_code=400, detail="Invalid session_id format")
        repo_name = request.repo_url or settings.TARGET_REPO or "this repository"

        # Enforce rate limit using authenticated user identity
        user_id = user.get("sub", "anonymous")
        if not check_rate_limit(agent.retriever.graph_store.driver, user_id, max_queries=settings.RATE_LIMIT_MAX):
            return JSONResponse(
                status_code=429,
                content={"detail": f"Daily query limit of {settings.RATE_LIMIT_MAX} reached. Try again tomorrow."},
            )

        # If a session_id is provided, require that the repo was prepared (docs collection exists).
        if session_id:
            try:
                ready = agent.retriever.vector_store.has_session_collection(session_id)
            except Exception:
                ready = False
            if not ready:
                return {
                    "status": "needs_ingestion",
                    "message": "Repository is not prepared for this session_id. Call /v1/prepare-repo first.",
                    "metadata": {"session_id": session_id},
                }
        initial_state = {
            "query": request.user_query,
            "original_query": request.user_query,
            "rewritten_query": "",
            "repo_name": repo_name,
            "session_id": session_id or "",
            "detected_feature": "",
            "documents": [],
            "code_results": [],
            "github_issues": [],
            "web_results": [],
            "response": "",
            "is_relevant": True,
            "is_hallucination": False,
            "iteration": 0,
            "allow_web_search": bool(request.allow_web_search),
        }
        config = {"configurable": {"thread_id": session_id or "default"}}
        result = cast(Any, agent.app).invoke(initial_state, config=config)

        agent.prune_history(session_id or "default")

        return {
            "status": "success",
            "answer": result["response"],
            "metadata": {
                "detected_feature": result["detected_feature"],
                "docs_retrieved": len(result["documents"]),
                "github_issues_found": len(result["github_issues"]),
                "session_id": session_id,
                "is_relevant": bool(result.get("is_relevant", True)),
            },
        }
    except Exception as e:
        # Decrement rate limit counter on failure so quota isn't consumed
        try:
            decrement_rate_limit(agent.retriever.graph_store.driver, user_id)
        except Exception:
            logger.warning("Failed to decrement rate limit on error", extra={"user_id": user_id})
        logger.exception("Error while solving ticket")
        raise HTTPException(status_code=500, detail=str(e))


def _set_status(session_id: str, stage: str, message: str = "") -> None:
    _SESSION_STATUS[session_id] = {
        "session_id": session_id,
        "stage": stage,
        "message": message,
    }


def _set_status_ex(
    session_id: str,
    stage: str,
    message: str = "",
    *,
    percent: int | None = None,
    current: int | None = None,
    total: int | None = None,
    eta_seconds: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "session_id": session_id,
        "stage": stage,
        "message": message,
    }
    if percent is not None:
        payload["percent"] = int(max(0, min(100, percent)))
    if current is not None:
        payload["current"] = int(current)
    if total is not None:
        payload["total"] = int(total)
    if eta_seconds is not None:
        payload["eta_seconds"] = int(max(0, eta_seconds))
    _SESSION_STATUS[session_id] = payload


def _index_code_chunks(
    chunks: list,
    session_id: str,
    report: Callable,
    vector_store: Any = None,
) -> None:
    from database.vector_store import VectorStore
    from ingestion.code_indexer import CodeChunk
    from qdrant_client.models import Distance, VectorParams, PointStruct

    if vector_store is None:
        vector_store = VectorStore()
    collection_name = f"code_{session_id}" if session_id else "code_default"

    try:
        vector_store.client.get_collection(collection_name)
    except Exception:
        vector_store.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )

    total = len(chunks)
    batch_size = 64

    for start in range(0, total, batch_size):
        end = min(total, start + batch_size)
        batch = chunks[start:end]

        texts = [c.docstring or c.signature or c.symbol_name for c in batch]
        vectors = vector_store.embeddings.embed_documents(texts)

        points = []
        for j, chunk in enumerate(batch):
            idx = start + j
            points.append(PointStruct(
                id=idx,
                vector=vectors[j],
                payload={
                    "text": texts[j],
                    "symbol_name": chunk.symbol_name,
                    "symbol_type": chunk.symbol_type,
                    "signature": chunk.signature,
                    "file_path": chunk.file_path,
                    "line_start": chunk.line_start,
                    "line_end": chunk.line_end,
                    "source_code": chunk.source_code,
                    "type": "code",
                    "session_id": session_id,
                },
            ))

        vector_store.client.upsert(collection_name=collection_name, points=points)
        report("indexing_code", end, total, f"Indexing code ({end}/{total})")


def _prepare_repo_task(repo_url: str, github_token: str | None, session_id: str) -> None:
    # Validate session_id to prevent path traversal
    validated_session_id = validate_session_id(session_id)
    if not validated_session_id:
        logger.error(
            "Invalid session_id in _prepare_repo_task",
            extra={"session_id": session_id[:50]},
        )
        _set_status_ex(session_id, "error", "Invalid session_id format", percent=100)
        return
    session_id = validated_session_id
    try:
        # Overall progress weights — phases 3/4/5 run in parallel after phase 2.
        PHASES = {
            "cloning": 5,
            "parsing_docs": 20,
            "indexing_docs": 35,
            "indexing_code": 10,
            "building_graph": 30,
        }
        phase_order = list(PHASES.keys())
        phase_base: dict[str, int] = {}
        acc = 0
        for p in phase_order:
            phase_base[p] = acc
            acc += PHASES[p]

        phase_started_at: dict[str, float] = {}

        def report(phase: str, current: int, total: int, message: str) -> None:
            w = PHASES.get(phase, 0)
            base = phase_base.get(phase, 0)
            if phase not in phase_started_at:
                phase_started_at[phase] = time.time()
            pct_in_phase = 0
            if total > 0:
                pct_in_phase = int((current / total) * 100)
            overall = base + int((pct_in_phase / 100) * w)

            eta = None
            started = phase_started_at.get(phase)
            if started and total > 0 and current > 0:
                elapsed = time.time() - started
                rate = current / max(0.001, elapsed)
                remaining = max(0, total - current)
                eta = int(remaining / max(0.001, rate))

            _set_status_ex(
                session_id,
                phase,
                message,
                percent=overall,
                current=current,
                total=total,
                eta_seconds=eta,
            )

        # ── Phase 1: Clone ─────────────────────────────────────
        report("cloning", 0, 1, f"Preparing local repo for {repo_url}")
        local_path = str(RAW_DOCS_DIR / session_id)

        docs_loader = DocsLoader(
            repo_url=repo_url,
            github_token=github_token,
            local_path=local_path,
            session_id=session_id,
            progress_cb=report,
        )
        report("cloning", 1, 1, "Repository available locally")

        # ── Phase 2: Parse docs ────────────────────────────────
        report("parsing_docs", 0, 1, "Loading and splitting docs")
        chunks = docs_loader.load_and_split()

        # ── Phases 3/4/5: Index docs, index code, build graph (parallel) ──
        parallel_base = phase_base["indexing_docs"]

        def _run_index_docs():
            report("indexing_docs", 0, max(1, len(chunks)), "Indexing docs into Qdrant")
            docs_loader.upload_to_qdrant(chunks)

        def _run_index_code():
            if not (settings.AST_ENABLED and settings.LOCAL_MODE):
                return
            from ingestion.code_indexer import CodeIndexer

            report("indexing_code", 0, 1, "Indexing Python source code")
            code_indexer = CodeIndexer()

            repo_root = Path(str(RAW_DOCS_DIR / session_id))
            src_root = repo_root
            for candidate in [repo_root / "src", repo_root / "lib", repo_root]:
                if candidate.is_dir():
                    src_root = candidate
                    break

            code_chunks = code_indexer.index_directory(src_root, exclude_dirs=settings.AST_EXCLUDE_DIRS)
            report("indexing_code", 0, max(1, len(code_chunks)), f"Found {len(code_chunks)} code symbols")

            if code_chunks:
                _index_code_chunks(
                    code_chunks, session_id, report,
                    vector_store=agent.retriever.vector_store,
                )

        def _run_build_graph():
            report("building_graph", 0, 20, "Building Neo4j issue graph")
            gh_loader = GitHubGraphLoader(
                repo_url=repo_url,
                token=github_token,
                session_id=session_id,
                progress_cb=report,
            )
            gh_loader.run()

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(_run_index_docs): "indexing_docs",
                pool.submit(_run_index_code): "indexing_code",
                pool.submit(_run_build_graph): "building_graph",
            }
            for future in as_completed(futures):
                phase_name = futures[future]
                try:
                    future.result()
                except Exception:
                    logger.exception(f"Parallel phase {phase_name} failed")
                    raise

        _set_status_ex(session_id, "complete", "Repository prepared", percent=100)
    except Exception as e:
        logger.exception("Repo preparation failed", extra={"session_id": session_id, "error_type": type(e).__name__})
        _set_status_ex(session_id, "error", "Repository preparation failed", percent=100)


@app.post("/v1/prepare-repo", dependencies=[Depends(get_current_user)])
async def prepare_repo(
    request: PrepareRepoRequest,
    background_tasks: BackgroundTasks,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    session_id = x_session_id or request.session_id
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    session_id = validate_session_id(session_id)
    if not session_id:
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    _set_status(session_id, "queued", "Repo preparation queued")
    background_tasks.add_task(_prepare_repo_task, request.repo_url, request.github_token, session_id)
    return {"status": "processing", "metadata": {"session_id": session_id}}


@app.get("/v1/status/{session_id}", dependencies=[Depends(get_current_user)])
async def get_status(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    session_id = validate_session_id(session_id)
    if not session_id:
        raise HTTPException(status_code=400, detail="Invalid session_id format")
    status = _SESSION_STATUS.get(session_id)
    if not status:
        return {"status": "needs_ingestion", "metadata": {"session_id": session_id}}
    return {"status": "ok", "data": status}


@app.post("/v1/cleanup/{session_id}", dependencies=[Depends(get_current_user)])
async def cleanup_session(session_id: str):
    session_id = validate_session_id(session_id)
    if not session_id:
        raise HTTPException(status_code=400, detail="Invalid session_id format")
    try:
        agent.cleanup_session(session_id)
        _SESSION_STATUS.pop(session_id, None)
        return {"status": "success"}
    except Exception as e:
        logger.exception("Cleanup failed", extra={"session_id": session_id})
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/feedback", dependencies=[Depends(get_current_user)])
async def submit_feedback(request: FeedbackRequest):
    try:
        _feedback_store.store_feedback(
            query=request.query,
            answer=request.answer,
            feature=request.feature_detected,
            thumbs_up=request.thumbs_up,
            session_id=request.session_id,
        )
        return {"status": "ok"}
    except Exception as e:
        logger.exception("Feedback storage failed")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
