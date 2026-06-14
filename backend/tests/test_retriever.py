from unittest.mock import patch, MagicMock

from database.hybrid_retriever import HybridRetriever


def test_retriever_uses_neo4j_id_from_docs():
    with (
        patch("database.hybrid_retriever.VectorStore") as mock_vector_store,
        patch("database.hybrid_retriever.GraphStore") as mock_graph_store,
    ):
        mock_vector_store.return_value.search.return_value = [
            {"neo4j_id": "Feature123"}
        ]

        retriever = HybridRetriever()
        retriever.retrieve_all("example query")

        mock_graph_store.return_value.get_related_issues.assert_called_once_with(
            "Feature123"
        )


def test_rerank_returns_top_k():
    with (
        patch("database.hybrid_retriever.VectorStore"),
        patch("database.hybrid_retriever.GraphStore"),
    ):
        retriever = HybridRetriever()
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.1, 0.9, 0.5, 0.7]
        retriever._reranker = mock_model

        docs = [
            {"text": "doc1", "source": "a.md"},
            {"text": "doc2", "source": "b.md"},
            {"text": "doc3", "source": "c.md"},
            {"text": "doc4", "source": "d.md"},
        ]
        result = retriever.rerank("test query", docs, top_k=2)

        assert len(result) == 2
        assert result[0]["source"] == "b.md"  # highest score 0.9
        assert result[1]["source"] == "d.md"  # second highest 0.7


def test_rerank_skips_invalid_docs():
    with (
        patch("database.hybrid_retriever.VectorStore"),
        patch("database.hybrid_retriever.GraphStore"),
    ):
        retriever = HybridRetriever()
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.5]
        retriever._reranker = mock_model

        docs = [
            {"text": "valid doc"},
            {"source": "no_text_key"},
            "plain_string",
        ]
        result = retriever.rerank("test query", docs, top_k=3)

        assert len(result) == 1
        assert result[0]["text"] == "valid doc"


def test_top3_neo4j_id_uses_first_non_general():
    with (
        patch("database.hybrid_retriever.VectorStore") as mock_vector_store,
        patch("database.hybrid_retriever.GraphStore") as mock_graph_store,
    ):
        mock_vector_store.return_value.search.return_value = [
            {"neo4j_id": "General", "source": "index.md", "text": "Welcome"},
            {"neo4j_id": "cli", "source": "cli/install.md", "text": "CLI install"},
            {"neo4j_id": "cli", "source": "cli/commands.md", "text": "CLI commands"},
        ]

        retriever = HybridRetriever()
        retriever.retrieve_all("install cli", detected_feature=None)

        mock_graph_store.return_value.get_related_issues.assert_called_once_with("cli")


def test_top3_all_general_falls_through_to_detected():
    with (
        patch("database.hybrid_retriever.VectorStore") as mock_vector_store,
        patch("database.hybrid_retriever.GraphStore") as mock_graph_store,
    ):
        mock_vector_store.return_value.search.return_value = [
            {"neo4j_id": "General", "source": "index.md", "text": "Welcome"},
            {"neo4j_id": "General", "source": "about.md", "text": "About"},
        ]

        retriever = HybridRetriever()
        retriever.retrieve_all("login", detected_feature="auth")

        mock_graph_store.return_value.get_related_issues.assert_called_once_with("auth")


def test_top3_empty_docs_no_crash():
    with (
        patch("database.hybrid_retriever.VectorStore") as mock_vector_store,
        patch("database.hybrid_retriever.GraphStore"),
    ):
        mock_vector_store.return_value.search.return_value = []

        retriever = HybridRetriever()
        result = retriever.retrieve_all("test", detected_feature="none")

        assert len(result["known_issues"]) == 0
        assert len(result["official_docs"]) == 0


def test_text_fallback_activated_when_all_bridges_fail():
    with (
        patch("database.hybrid_retriever.VectorStore") as mock_vector_store,
        patch("database.hybrid_retriever.GraphStore") as mock_graph_store,
    ):
        mock_vector_store.return_value.search.return_value = [
            {"neo4j_id": "General", "source": "index.md", "text": "Welcome"},
        ]
        mock_graph_store.return_value.get_related_issues_by_text.return_value = [
            "#201: Connection timeout error",
        ]

        retriever = HybridRetriever()
        result = retriever.retrieve_all("timeout error", detected_feature="None")

        mock_graph_store.return_value.get_related_issues_by_text.assert_called_once()
        assert len(result["known_issues"]) == 1
        assert "timeout" in result["known_issues"][0]


def test_text_fallback_skipped_for_short_query():
    with (
        patch("database.hybrid_retriever.VectorStore") as mock_vector_store,
        patch("database.hybrid_retriever.GraphStore") as mock_graph_store,
    ):
        mock_vector_store.return_value.search.return_value = [
            {"neo4j_id": "General", "source": "index.md", "text": "Welcome"},
        ]

        retriever = HybridRetriever()
        result = retriever.retrieve_all("ok", detected_feature="None")

        mock_graph_store.return_value.get_related_issues_by_text.assert_not_called()
        assert len(result["known_issues"]) == 0


def test_reranker_fallback_on_import_error():
    with (
        patch("database.hybrid_retriever.VectorStore"),
        patch("database.hybrid_retriever.GraphStore"),
        patch("sentence_transformers.CrossEncoder", side_effect=Exception("Model unavailable")),
    ):
        retriever = HybridRetriever()
        reranker = retriever._get_reranker()
        assert reranker is None
        # Second call should return cached False
        assert retriever._get_reranker() is None


def test_rerank_no_text_key_returns_early():
    with (
        patch("database.hybrid_retriever.VectorStore"),
        patch("database.hybrid_retriever.GraphStore"),
    ):
        retriever = HybridRetriever()
        retriever._reranker = MagicMock()  # make it non-None so rerank doesn't skip
        docs = [{"no_text": "value"}]
        result = retriever.rerank("test query", docs, top_k=3)
        # No valid docs with "text" key → empty result
        assert len(result) == 0
        # predict should not be called because len(valid) < 2
        retriever._reranker.predict.assert_not_called()
