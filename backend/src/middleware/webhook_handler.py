import hashlib
import os
import re
import requests

from langchain_text_splitters import MarkdownHeaderTextSplitter

from database.vector_store import VectorStore
from database.graph_store import GraphStore
from utils.logging_config import setup_logging

from qdrant_client.models import PointStruct

logger = setup_logging(__name__)

FEATURE_NAME_PATTERN = re.compile(r"^[\w\s-]{1,128}$")


def _make_point_id(key: str) -> int:
    """Deterministic point ID via MD5 (not used for security, just determinism)."""
    return int(hashlib.md5(key.encode()).hexdigest(), 16) & 0x7FFFFFFFFFFFFFFF


def _validate_feature_name(name: str) -> str | None:
    """Validate feature name to prevent Cypher injection."""
    if not name:
        return None
    if not FEATURE_NAME_PATTERN.match(name):
        logger.warning(
            "Invalid feature_name format, discarding",
            extra={"feature_name": name[:100]},
        )
        return None
    return name.strip()


def _parse_repo(payload: dict) -> tuple[str, str, str, str]:
    """Extract owner, repo name, default branch, and full_name from push payload."""
    repo = payload.get("repository", {})
    owner_info = repo.get("owner", {})
    owner = owner_info.get("login", owner_info.get("name", ""))
    repo_name = repo.get("name", "")
    branch = repo.get("default_branch", "main")
    full_name = repo.get("full_name", f"{owner}/{repo_name}")
    return owner, repo_name, branch, full_name


def _download_raw_file(owner: str, repo: str, branch: str, file_path: str) -> str | None:
    """Download a file from raw.githubusercontent.com."""
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    except Exception:
        logger.exception("Failed to download file", extra={"url": url, "file": file_path})
        return None


def _split_markdown(content: str, source_label: str) -> list[dict]:
    """Split markdown content into chunks with metadata."""
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    chunks = splitter.split_text(content)
    result = []
    for chunk in chunks:
        result.append({
            "text": chunk.page_content,
            "source": source_label,
            "feature_name": "General",
            "feature": "General",
            "neo4j_id": "General",
        })
    return result


def _embed_and_upsert(
    vector_store: VectorStore,
    chunks: list[dict],
    session_id: str | None,
) -> None:
    """Embed text chunks and upsert into Qdrant."""
    if not chunks:
        return
    texts = [c["text"] for c in chunks]
    vectors = vector_store.embeddings.embed_documents(texts)
    collection = (
        f"docs_{session_id}" if session_id else vector_store.collection_name
    )
    try:
        vector_store.client.get_collection(collection)
    except Exception:
        from qdrant_client.models import Distance, VectorParams
        vector_store.client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
    try:
        vector_store.client.create_payload_index(
            collection_name=collection,
            field_name="session_id",
            field_schema="keyword",
        )
    except Exception:
        pass
    points = []
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        points.append(
            PointStruct(
                id=_make_point_id(f"{chunk['source']}:{i}"),
                vector=vec,
                payload={
                    "text": chunk["text"],
                    "source": chunk["source"],
                    "feature_name": chunk.get("feature_name", "General"),
                    "feature": chunk.get("feature", "General"),
                    "neo4j_id": chunk.get("neo4j_id", "General"),
                    "session_id": session_id,
                },
            )
        )
    vector_store.client.upsert(collection_name=collection, points=points)
    logger.info("Webhook upserted chunks", extra={"count": len(points), "collection": collection})


def handle_push(payload: dict, session_id: str | None = None) -> None:
    """Re-index changed .md files from a push event."""
    owner, repo_name, branch, full_name = _parse_repo(payload)
    commits = payload.get("commits", [])
    changed_md_files: set[str] = set()
    for commit in commits:
        for file in commit.get("added", []) + commit.get("modified", []):
            if file.endswith(".md"):
                changed_md_files.add(file)

    if not changed_md_files:
        logger.info("Push event: no .md files changed")
        return

    vector_store = VectorStore()

    for file_path in changed_md_files:
        logger.info("Re-indexing changed file", extra={"file": file_path})
        content = _download_raw_file(owner, repo_name, branch, file_path)
        if content is None:
            continue
        vector_store.delete_by_metadata({"source": file_path}, session_id=session_id)
        chunks = _split_markdown(content, file_path)
        _embed_and_upsert(vector_store, chunks, session_id)

    logger.info(
        "Push handling complete",
        extra={"files_reindexed": len(changed_md_files), "session_id": session_id},
    )


def handle_issue_event(payload: dict, session_id: str | None = None) -> None:
    """Update Neo4j graph when a GitHub issue is opened/closed/reopened/edited."""
    issue = payload.get("issue", {})
    if not issue:
        logger.warning("Issue event missing 'issue' field")
        return

    action = payload.get("action", "opened")
    if action == "deleted":
        logger.info("Skipping deleted issue", extra={"issue": issue.get("number")})
        return

    graph_store = GraphStore()
    graph_store.upsert_issue(issue, session_id=session_id)

    body = issue.get("body", "") or ""
    match = re.search(r"(?i)(?:feature|component):\s*(\S.+)", body)
    if match:
        feature_name = match.group(1).strip().rstrip(".")
        validated_name = _validate_feature_name(feature_name)
        if validated_name:
            graph_store.upsert_issue_affects(
                issue.get("number", 0), validated_name, session_id=session_id,
            )

    logger.info(
        "Issue event handled",
        extra={
            "issue": issue.get("number"),
            "action": action,
            "session_id": session_id,
        },
    )


def _link_pr_to_issues(graph_store, pr_number: int, body: str, session_id: str | None) -> None:
    """Extract issue references from PR body and link via FIXED_BY."""
    issue_numbers = re.findall(r"(?:close|fix|resolve)[sd]?\s+#(\d+)", body, re.IGNORECASE)
    if not issue_numbers:
        issue_numbers = re.findall(r"#(\d+)", body)
    for issue_num in issue_numbers[:5]:
        try:
            query = """
            MATCH (i:Issue {neo4j_id: $issue_number})
            MERGE (p:PR {neo4j_id: $pr_number})
            MERGE (i)-[:FIXED_BY]->(p)
            SET p.session_id = $session_id
            """
            with graph_store.driver.session() as session:
                session.run(
                    query,
                    issue_number=issue_num,
                    pr_number=str(pr_number),
                    session_id=session_id,
                )
        except Exception:
            logger.exception("Failed to link issue to PR", extra={"issue": issue_num, "pr": pr_number})


def handle_pr_event(payload: dict, session_id: str | None = None) -> None:
    """Update Neo4j graph when a PR is opened/closed/edited."""
    pr = payload.get("pull_request", {})
    if not pr:
        logger.warning("PR event missing 'pull_request' field")
        return

    action = payload.get("action", "opened")
    if action == "deleted":
        logger.info("Skipping deleted PR", extra={"pr": pr.get("number")})
        return

    merged = bool(pr.get("merged", False))
    if action not in ("opened", "edited") and not (action == "closed" and merged):
        logger.info("Skipping PR event", extra={"action": action, "pr": pr.get("number")})
        return

    graph_store = GraphStore()

    pr_data = {
        "number": pr.get("number", 0),
        "title": pr.get("title", ""),
        "state": "merged" if merged else pr.get("state", "open"),
        "merged": merged,
        "html_url": pr.get("html_url", ""),
        "created_at": str(pr.get("created_at", "")),
        "merged_at": str(pr.get("merged_at") or ""),
    }
    graph_store.upsert_pr(pr_data, session_id=session_id)

    body = pr.get("body", "") or ""
    _link_pr_to_issues(graph_store, pr.get("number", 0), body, session_id)

    if pr.get("changed_files", 0) > 0:
        files_data = payload.get("files", pr.get("files", []))
        if not files_data:
            try:
                import requests
                pr_url = pr.get("url", "")
                if pr_url:
                    token = os.getenv("GITHUB_TOKEN")
                    headers = {"Authorization": f"Bearer {token}"} if token else {}
                    resp = requests.get(f"{pr_url}/files", headers=headers, timeout=30)
                    resp.raise_for_status()
                    files_data = resp.json()
            except Exception:
                logger.exception("Failed to fetch PR files")
        if files_data:
            file_paths = [f.get("filename", "") for f in files_data]
            graph_store.upsert_pr_files(pr.get("number", 0), file_paths, session_id=session_id)

    logger.info(
        "PR event handled",
        extra={
            "pr": pr.get("number"),
            "action": action,
            "merged": merged,
            "session_id": session_id,
        },
    )
