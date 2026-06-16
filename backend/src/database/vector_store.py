from typing import Any, Iterable, cast

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

from utils.logging_config import setup_logging
from settings import settings

logger = setup_logging(__name__)


class VectorStore:
    def __init__(self):
        qdrant_url = self._sanitize_qdrant_url(settings.QDRANT_URL)
        qdrant_api_key = settings.QDRANT_API_KEY

        # Use in-memory Qdrant if no URL is provided
        if not qdrant_url or qdrant_url == "http://localhost:6333":
            self.client = QdrantClient(":memory:")
            logger.info("Using in-memory Qdrant client")
        else:
            # Network hardening for cloud connectivity.
            self.client = QdrantClient(
                url=qdrant_url,
                api_key=qdrant_api_key,
                timeout=60,
                check_compatibility=False,
            )
            logger.info("Using Qdrant client", extra={"url": qdrant_url})
        self.embeddings = FastEmbedEmbeddings(
            model_name="BAAI/bge-small-en-v1.5",
            threads=settings.ONNX_THREADS,
        )
        # Default collection name should not assume any particular target project.
        self.collection_name = (settings.QDRANT_COLLECTION or "docs_default").strip() or "docs_default"

    def _sanitize_qdrant_url(self, url: str | None) -> str | None:
        if not url:
            return None
        u = url.strip().rstrip("/")
        if not u:
            return None
        # Accept either full URL or hostname:port.
        if u.startswith("http://") or u.startswith("https://"):
            return u
        return f"http://{u}"

    def _collection_for_session(self, session_id: str | None) -> str:
        if session_id:
            return f"docs_{session_id}"
        return self.collection_name

    def _session_filter(self, session_id: str | None) -> Filter | None:
        if not session_id:
            return None
        return Filter(
            must=[
                FieldCondition(
                    key="session_id",
                    match=MatchValue(value=session_id),
                )
            ]
        )

    def search(self, query: str, limit: int = 3, session_id: str | None = None, _retried: bool = False):
        """Performs semantic search on the documentation."""
        query_vector = self.embeddings.embed_query(query)
        client: Any = self.client
        search_fn = getattr(client, "search", None)
        q_filter = self._session_filter(session_id)
        collection = self._collection_for_session(session_id)
        try:
            if callable(search_fn):
                try:
                    raw_points = search_fn(
                        collection_name=collection,
                        query_vector=query_vector,
                        limit=limit,
                        query_filter=q_filter,
                    )
                except TypeError:
                    raw_points = search_fn(
                        collection_name=collection,
                        query_vector=query_vector,
                        limit=limit,
                        filter=q_filter,
                    )
                logger.debug("Qdrant search used")
                points = list(cast(Iterable[Any], raw_points))
            else:
                try:
                    response = client.query_points(
                        collection_name=collection,
                        query=query_vector,
                        limit=limit,
                        query_filter=q_filter,
                    )
                except TypeError:
                    response = client.query_points(
                        collection_name=collection,
                        query=query_vector,
                        limit=limit,
                        filter=q_filter,
                    )
                logger.debug("Qdrant query_points used")
                raw_points = getattr(response, "points", [])
                points = list(cast(Iterable[Any], raw_points))
        except Exception as exc:
            err_str = str(exc)
            if "Index required" in err_str and "session_id" in err_str and not _retried:
                logger.warning("Missing session_id payload index — creating it and retrying")
                try:
                    client.create_payload_index(
                        collection_name=collection,
                        field_name="session_id",
                        field_schema="keyword",
                    )
                except Exception:
                    logger.debug("Failed to create payload index, searching without filter")
                    return self.search(query, limit=limit, session_id=None, _retried=True)
                return self.search(query, limit=limit, session_id=session_id, _retried=True)
            if "Index required" in err_str and "session_id" in err_str:
                logger.warning("Fallback: searching without session filter")
                return self.search(query, limit=limit, session_id=None, _retried=True)
            raise
        results = []
        for res in points:
            payload = getattr(res, "payload", None) or {}
            results.append(
                {
                    "text": payload.get("text", ""),
                    "source": payload.get("source", "unknown"),
                    "feature_name": payload.get("feature_name")
                    or payload.get("feature")
                    or "General",
                    "neo4j_id": payload.get("neo4j_id")
                    or payload.get("feature_name")
                    or payload.get("feature")
                    or "General",
                    "score": getattr(res, "score", None),
                }
            )
        return results

    def search_code(self, query: str, limit: int = 3, session_id: str | None = None):
        """Performs semantic search on code index."""
        query_vector = self.embeddings.embed_query(query)
        client: Any = self.client
        collection = f"code_{session_id}" if session_id else "code_default"

        try:
            search_fn = getattr(client, "search", None)
            if callable(search_fn):
                raw_points = search_fn(
                    collection_name=collection,
                    query_vector=query_vector,
                    limit=limit,
                )
            else:
                response = client.query_points(
                    collection_name=collection,
                    query=query_vector,
                    limit=limit,
                )
                raw_points = response.points

            results = []
            for res in raw_points:
                payload = getattr(res, "payload", None) or {}
                results.append({
                    "text": payload.get("text", ""),
                    "symbol_name": payload.get("symbol_name", ""),
                    "symbol_type": payload.get("symbol_type", ""),
                    "signature": payload.get("signature", ""),
                    "file_path": payload.get("file_path", ""),
                    "line_start": payload.get("line_start"),
                    "line_end": payload.get("line_end"),
                    "source_code": payload.get("source_code", ""),
                    "score": getattr(res, "score", None),
                })
            return results
        except Exception:
            logger.debug("Code collection not found or search failed", exc_info=True)
            return []

    def cleanup_session(self, session_id: str) -> None:
        """Deletes the session-scoped collection (preferred) and falls back to filtered deletes."""
        client: Any = self.client

        collection = self._collection_for_session(session_id)
        delete_collection_fn = getattr(client, "delete_collection", None)
        if callable(delete_collection_fn):
            try:
                delete_collection_fn(collection_name=collection)
                return
            except Exception:
                logger.exception(
                    "Qdrant delete_collection failed",
                    extra={"collection": collection},
                )

        # Fallback for older behavior: delete points in default collection tagged with session_id.
        q_filter = self._session_filter(session_id)
        if q_filter is None:
            return
        for method_name, kwargs in (
            ("delete", {"collection_name": self.collection_name, "filter": q_filter}),
            ("delete", {"collection_name": self.collection_name, "points_selector": q_filter}),
            ("delete_points", {"collection_name": self.collection_name, "filter": q_filter}),
        ):
            fn = getattr(client, method_name, None)
            if not callable(fn):
                continue
            try:
                fn(**kwargs)
                return
            except TypeError:
                continue
            except Exception:
                logger.exception(
                    "Qdrant session cleanup failed",
                    extra={"method": method_name, "collection": self.collection_name},
                )
                return

    def delete_by_metadata(self, metadata_filter: dict, session_id: str | None = None) -> None:
        """Delete points matching a metadata filter (e.g. {"source": "docs/foo.md"})."""
        client: Any = self.client
        collection = self._collection_for_session(session_id)
        conditions = [
            FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in metadata_filter.items()
        ]
        q_filter = Filter(must=conditions) if conditions else None
        if q_filter is None:
            return

        try:
            scroll_fn = getattr(client, "scroll", None)
            if callable(scroll_fn):
                points, _ = scroll_fn(
                    collection_name=collection,
                    scroll_filter=q_filter,
                    limit=100,
                )
                point_ids = [p.id for p in points]
                if point_ids:
                    client.delete(
                        collection_name=collection,
                        points_selector=point_ids,
                    )
                    logger.info(
                        "Deleted Qdrant points by metadata",
                        extra={"filter": metadata_filter, "count": len(point_ids)},
                    )
        except Exception:
            logger.exception(
                "Qdrant delete_by_metadata failed",
                extra={"filter": metadata_filter},
            )

    def has_session_collection(self, session_id: str) -> bool:
        client: Any = self.client
        get_collection_fn = getattr(client, "get_collection", None)
        if not callable(get_collection_fn):
            return False
        try:
            get_collection_fn(self._collection_for_session(session_id))
            return True
        except Exception:
            return False
