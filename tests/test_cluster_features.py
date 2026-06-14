import numpy as np

from ingestion.cluster_features import FeatureClusterer


class TestFeatureClusterer:
    def test_fit_predict_returns_labels(self):
        texts = [
            "how to configure CORS middleware in FastAPI",
            "setup CORS and middleware options",
            "CORS configuration for multiple origins",
            "error handling with HTTPException",
            "custom exception handler setup",
            "handling validation errors",
            "how to use dependency injection",
            "Depends and sub-dependencies",
            "dependency injection with yield",
        ]
        rng = np.random.default_rng(42)
        embeddings = rng.random((len(texts), 384))

        clusterer = FeatureClusterer(min_cluster_size=2)
        results = clusterer.fit_predict(embeddings, texts)

        assert len(results) == len(texts)
        for label, cluster_id in results:
            assert isinstance(label, str)
            assert len(label) > 0
            assert isinstance(cluster_id, int)

    def test_small_dataset_returns_general(self):
        texts = ["just one chunk about something"]
        rng = np.random.default_rng(1)
        embeddings = rng.random((1, 384))

        clusterer = FeatureClusterer(min_cluster_size=5)
        results = clusterer.fit_predict(embeddings, texts)

        assert len(results) == 1
        label, cluster_id = results[0]
        assert label == "General"
        assert cluster_id == -1

    def test_always_returns_correct_count(self):
        texts = ["a", "b", "c", "d"]
        rng = np.random.default_rng(1)
        embeddings = rng.random((4, 384))
        clusterer = FeatureClusterer(min_cluster_size=2)
        results = clusterer.fit_predict(embeddings, texts)
        assert len(results) == 4

    def test_labels_are_readable(self):
        texts = [
            "install fastapi with pip and setup",
            "quickstart guide for fastapi",
            "how to install and run fastapi",
            "deploy fastapi on production server",
            "running fastapi with uvicorn gunicorn",
            "production deployment configuration",
        ]
        rng = np.random.default_rng(42)
        embeddings = rng.random((len(texts), 384))

        clusterer = FeatureClusterer(min_cluster_size=2)
        results = clusterer.fit_predict(embeddings, texts)

        for label, cluster_id in results:
            if cluster_id != -1:
                terms = label.split(", ")
                assert all(len(t) > 0 for t in terms)
                assert all(t.islower() for t in terms)
