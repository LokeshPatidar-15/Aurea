from pathlib import Path

import numpy as np

ST_DEFAULT = "sentence-transformers/all-MiniLM-L6-v2"


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return (matrix / np.where(norms == 0, 1.0, norms)).astype(np.float32)


class LsaEmbedder:
    name = "lsa"

    def __init__(self, dim: int = 128):
        self.dim = dim
        self.pipeline = None

    def fit(self, texts: list) -> "LsaEmbedder":
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vectorizer = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), stop_words="english", min_df=1)
        tfidf = self.vectorizer.fit_transform(texts)
        components = max(2, min(self.dim, tfidf.shape[0] - 1, tfidf.shape[1] - 1))
        self.svd = TruncatedSVD(n_components=components, random_state=0).fit(tfidf)
        self.pipeline = True
        return self

    def encode(self, texts: list) -> np.ndarray:
        return _normalize(self.svd.transform(self.vectorizer.transform(texts)))

    def save(self, folder: Path) -> None:
        import joblib

        joblib.dump({"vectorizer": self.vectorizer, "svd": self.svd, "dim": self.dim}, Path(folder) / "lsa.joblib")

    @classmethod
    def load(cls, folder: Path) -> "LsaEmbedder":
        import joblib

        state = joblib.load(Path(folder) / "lsa.joblib")
        obj = cls(state["dim"])
        obj.vectorizer, obj.svd, obj.pipeline = state["vectorizer"], state["svd"], True
        return obj


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = ST_DEFAULT):
        self.model_name = model_name
        self.name = f"st:{model_name}"
        self._model = None

    def _load(self):
        if self._model is None:
            import torch
            from sentence_transformers import SentenceTransformer

            torch.set_num_threads(1)
            self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    def fit(self, texts: list) -> "SentenceTransformerEmbedder":
        return self

    def encode(self, texts: list) -> np.ndarray:
        vectors = self._load().encode(list(texts), batch_size=32, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True)
        return vectors.astype(np.float32)

    def save(self, folder: Path) -> None:
        return None

    @classmethod
    def load(cls, folder: Path, name: str) -> "SentenceTransformerEmbedder":
        return cls(name.split(":", 1)[1])


def load_embedder(name: str, folder: Path):
    if name == "lsa":
        return LsaEmbedder.load(folder)
    if name.startswith("st:"):
        return SentenceTransformerEmbedder.load(folder, name)
    raise ValueError(f"unknown embedder {name!r}")
