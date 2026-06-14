from database.vector_store import VectorStore
from database.graph_store import GraphStore
from utils.logging_config import setup_logging

logger = setup_logging(__name__)


class HybridRetriever:
    def __init__(self):
        self.vector_store = VectorStore()
        self.graph_store = GraphStore()
        self._reranker = None

    def _get_reranker(self):
        if self._reranker is None:
            try:
                from sentence_transformers import CrossEncoder
                self._reranker = CrossEncoder("BAAI/bge-reranker-v2-m3")
            except Exception:
                logger.warning("Failed to load cross-encoder reranker. Reranking disabled.")
                self._reranker = False
        return self._reranker if self._reranker is not False else None

    def rerank(self, query: str, documents: list[dict], top_k: int = 3) -> list[dict]:
        reranker = self._get_reranker()
        if reranker is None:
            return documents[:top_k]

        valid = [d for d in documents if isinstance(d, dict) and "text" in d]
        if len(valid) < 2:
            return valid[:top_k]

        pairs = [[query, d["text"]] for d in valid]
        scores = reranker.predict(pairs)

        scored = list(zip(scores, valid))
        scored.sort(key=lambda x: x[0], reverse=True)

        return [doc for _, doc in scored[:top_k]]

    def retrieve_all(
        self,
        query: str,
        detected_feature: str | None = None,
        session_id: str | None = None,
    ):
        """Combines knowledge from both Vector and Graph databases."""
        docs = self.vector_store.search(query, session_id=session_id)
        code_results = self.vector_store.search_code(query, session_id=session_id)
        bugs = []
        top_neo4j_id = None
        if docs:
            for doc in docs[:3]:
                if isinstance(doc, dict):
                    nid = doc.get("neo4j_id")
                    if isinstance(nid, str) and nid.lower() != "general":
                        top_neo4j_id = nid
                        logger.debug(
                            "Found neo4j_id from doc",
                            extra={
                                "rank": docs.index(doc),
                                "neo4j_id": nid,
                                "source": doc.get("source", ""),
                            },
                        )
                        break
        if isinstance(top_neo4j_id, str) and top_neo4j_id.lower() != "general":
            if session_id:
                bugs = self.graph_store.get_related_issues(top_neo4j_id, session_id=session_id)
            else:
                bugs = self.graph_store.get_related_issues(top_neo4j_id)
        elif isinstance(detected_feature, str) and detected_feature.lower() != "none":
            if session_id:
                bugs = self.graph_store.get_related_issues(detected_feature, session_id=session_id)
            else:
                bugs = self.graph_store.get_related_issues(detected_feature)
        else:
            search_text = query.strip()
            if len(search_text) >= 3:
                logger.info("Falling back to text-based issue search", extra={"query": search_text})
                if session_id:
                    bugs = self.graph_store.get_related_issues_by_text(
                        search_text, limit=5, session_id=session_id
                    )
                else:
                    bugs = self.graph_store.get_related_issues_by_text(search_text, limit=5)
        logger.info(
            "Hybrid retrieval complete",
            extra={
                "docs_count": len(docs),
                "issues_count": len(bugs),
                "code_results_count": len(code_results),
                "feature_used": top_neo4j_id or detected_feature,
            },
        )

        return {"official_docs": docs, "code_results": code_results, "known_issues": bugs}

    def cleanup_session(self, session_id: str) -> None:
        # Best-effort: only removes session-tagged records.
        self.vector_store.cleanup_session(session_id)
        self.graph_store.cleanup_session(session_id)
