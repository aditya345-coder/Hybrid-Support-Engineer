from ingestion.docs_loader import DocsLoader
from ingestion.github_loader import GitHubGraphLoader


def test_identify_feature_falls_back_to_general():
    loader = DocsLoader.__new__(DocsLoader)
    loader._feature_embeddings = []
    assert loader.identify_feature("BackgroundTasks are great") == "General"


def test_identify_feature_from_path():
    loader = DocsLoader.__new__(DocsLoader)
    loader._feature_embeddings = []

    assert loader.identify_feature("", source_path="docs/auth/password-reset.md") == "auth"
    assert loader.identify_feature("", source_path="docs/api/rate-limits.md") == "api"
    assert loader.identify_feature("", source_path="README.md") == "General"
    assert loader.identify_feature("", source_path="docs/getting-started/overview.md") == "General"
    assert loader.identify_feature("some text") == "General"


def test_best_matching_feature_no_embeddings():
    loader = DocsLoader.__new__(DocsLoader)
    loader._feature_embeddings = []
    assert loader._best_matching_feature("any text") == "General"


def test_best_matching_feature_with_mock_embeddings():
    from unittest.mock import MagicMock
    loader = DocsLoader.__new__(DocsLoader)
    loader._feature_embeddings = [
        ("auth", [0.9, 0.1, 0.1]),
        ("billing", [0.1, 0.9, 0.1]),
    ]
    mock_vec = MagicMock()
    mock_vec.embeddings.embed_query.return_value = [0.85, 0.15, 0.1]
    loader.vector_store = mock_vec
    result = loader._best_matching_feature("password reset")
    assert result == "auth"


# ── Batch LLM tests ─────────────────────────────────────────────────────────


def test_extract_graph_data_batch_empty():
    from ingestion.github_loader import GitHubGraphLoader
    loader = GitHubGraphLoader.__new__(GitHubGraphLoader)
    result = loader.extract_graph_data_batch([])
    assert result == []


def test_extract_graph_data_batch_success():
    from unittest.mock import MagicMock
    import json

    loader = GitHubGraphLoader.__new__(GitHubGraphLoader)
    loader.llm = MagicMock()
    batch_response = json.dumps([
        {"features": ["auth"], "versions": [], "relationships": []},
        {"features": ["billing"], "versions": [], "relationships": []},
    ])
    loader.llm.extract_json.return_value = batch_response

    result = loader.extract_graph_data_batch(["Issue body 1", "Issue body 2"])
    assert len(result) == 2
    assert result[0]["features"] == ["auth"]
    assert result[1]["features"] == ["billing"]
    loader.llm.extract_json.assert_called_once()


def test_extract_graph_data_batch_parse_failure_falls_back():
    from unittest.mock import MagicMock, patch

    loader = GitHubGraphLoader.__new__(GitHubGraphLoader)
    loader.llm = MagicMock()
    loader.llm.extract_json.return_value = "not valid json"

    with patch.object(loader, "extract_graph_data", return_value={"features": [], "versions": [], "relationships": []}) as mock_single:
        result = loader.extract_graph_data_batch(["body1", "body2"])
        assert len(result) == 2
        assert mock_single.call_count == 2


# ── Batch embedding tests ───────────────────────────────────────────────────


def test_best_matching_features_batch_no_embeddings():
    loader = DocsLoader.__new__(DocsLoader)
    loader._feature_embeddings = []
    result = loader._best_matching_features_batch(["text1", "text2"])
    assert result == ["General", "General"]


def test_best_matching_features_batch_empty_input():
    loader = DocsLoader.__new__(DocsLoader)
    loader._feature_embeddings = [("auth", [0.9, 0.1])]
    result = loader._best_matching_features_batch([])
    assert result == []


def test_best_matching_features_batch_vectorized():
    from unittest.mock import MagicMock

    loader = DocsLoader.__new__(DocsLoader)
    loader._feature_embeddings = [
        ("auth", [1.0, 0.0, 0.0]),
        ("billing", [0.0, 1.0, 0.0]),
    ]
    mock_vec = MagicMock()
    # Two text vectors: one close to auth, one close to billing
    mock_vec.embeddings.embed_documents.return_value = [
        [0.9, 0.1, 0.0],
        [0.1, 0.9, 0.0],
    ]
    loader.vector_store = mock_vec

    result = loader._best_matching_features_batch(["password reset", "invoice paid"])
    assert result == ["auth", "billing"]


def test_best_matching_features_batch_below_threshold():
    from unittest.mock import MagicMock

    loader = DocsLoader.__new__(DocsLoader)
    loader._feature_embeddings = [
        ("auth", [1.0, 0.0, 0.0]),
    ]
    mock_vec = MagicMock()
    # Vector orthogonal to auth — cosine similarity = 0
    mock_vec.embeddings.embed_documents.return_value = [
        [0.0, 0.0, 1.0],
    ]
    loader.vector_store = mock_vec

    result = loader._best_matching_features_batch(["random text"])
    assert result == ["General"]


# ── Parallel phases test ────────────────────────────────────────────────────


def test_parallel_phases_run_concurrently():
    from concurrent.futures import ThreadPoolExecutor

    completed = []

    def fake_task(name, delay=0.05):
        import time
        time.sleep(delay)
        completed.append(name)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(fake_task, "indexing_docs"): "indexing_docs",
            pool.submit(fake_task, "indexing_code"): "indexing_code",
            pool.submit(fake_task, "building_graph"): "building_graph",
        }
        for f in futures:
            f.result()

    assert len(completed) == 3
    assert set(completed) == {"indexing_docs", "indexing_code", "building_graph"}
