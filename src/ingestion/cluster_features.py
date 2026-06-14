from __future__ import annotations

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer


class FeatureClusterer:
    def __init__(self, min_cluster_size: int = 5, random_state: int = 42):
        self.clusterer = HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric="euclidean",
            cluster_selection_epsilon=0.5,
            copy=True,
        )
        self.vectorizer = TfidfVectorizer(
            max_features=100, stop_words="english"
        )
        self.random_state = random_state

    def fit_predict(
        self, embeddings: np.ndarray, texts: list[str]
    ) -> list[tuple[str, int]]:
        if embeddings.shape[0] < 2:
            return [("General", -1)] * embeddings.shape[0]

        cluster_ids = self.clusterer.fit_predict(embeddings)

        labels: dict[int, str] = {}
        for cid in set(cluster_ids):
            if cid == -1:
                continue
            mask = cluster_ids == cid
            cluster_texts = [texts[i] for i in np.where(mask)[0]]
            try:
                tfidf = self.vectorizer.fit_transform(cluster_texts)
                terms = np.array(self.vectorizer.get_feature_names_out())
                scores = np.array(tfidf.sum(axis=0)).flatten()
                top_indices = np.argsort(scores)[-5:][::-1]
                top_terms = terms[top_indices]
                labels[int(cid)] = ", ".join(top_terms)
            except ValueError:
                labels[int(cid)] = "General"

        return [(labels.get(int(cid), "General"), int(cid)) for cid in cluster_ids]
