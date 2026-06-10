import math
import random
import re
import warnings
from collections.abc import Callable
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import silhouette_score

from app.core.config import Settings
from app.db.models import DatasetCandidateORM
from app.schemas.datasets import DatasetClusterRequest, DatasetSampleRequest
from app.services.datasets.serialization import candidate_text


def candidate_vectors(
    candidates: list[DatasetCandidateORM],
    settings: Settings,
    request: DatasetClusterRequest,
) -> tuple[list[list[float]], str]:
    semantic_vectors, backend = _minilm_vectors(candidates, settings)
    if semantic_vectors is None:
        semantic_vectors = _lexical_vectors(candidates)
        backend = "lexical"
    structured = _structured_vectors(candidates)
    semantic_weight = request.semantic_weight
    structured_weight = request.structured_weight
    vectors = []
    for semantic, struct in zip(semantic_vectors, structured, strict=True):
        vectors.append(
            _l2_normalize(
                [
                    *(value * semantic_weight for value in semantic),
                    *(value * structured_weight for value in struct),
                ]
            )
        )
    return vectors, backend


def _minilm_vectors(
    candidates: list[DatasetCandidateORM],
    settings: Settings,
) -> tuple[list[list[float]], str] | tuple[None, str]:
    model_dir = getattr(
        settings,
        "dataset_embedding_model_dir",
        settings.data_dir / "models" / "all-MiniLM-L6-v2",
    )
    model_dir = Path(model_dir)
    model_path = model_dir / "onnx" / "model_quantized.onnx"
    tokenizer_path = model_dir / "tokenizer.json"
    if not model_path.exists() or not tokenizer_path.exists():
        return None, "lexical"
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer
    except Exception:
        return None, "lexical"
    try:
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        texts = [candidate_text(candidate) for candidate in candidates]
        encodings = tokenizer.encode_batch(texts)
        max_length = min(max((len(encoding.ids) for encoding in encodings), default=1), 256)
        input_ids = []
        attention_mask = []
        token_type_ids = []
        for encoding in encodings:
            ids = encoding.ids[:max_length]
            mask = encoding.attention_mask[:max_length]
            types = encoding.type_ids[:max_length] if encoding.type_ids else [0] * len(ids)
            pad = max_length - len(ids)
            input_ids.append(ids + [0] * pad)
            attention_mask.append(mask + [0] * pad)
            token_type_ids.append(types + [0] * pad)
        feeds = {
            "input_ids": np.asarray(input_ids, dtype=np.int64),
            "attention_mask": np.asarray(attention_mask, dtype=np.int64),
        }
        input_names = {item.name for item in session.get_inputs()}
        if "token_type_ids" in input_names:
            feeds["token_type_ids"] = np.asarray(token_type_ids, dtype=np.int64)
        output = session.run(None, feeds)[0]
        mask = feeds["attention_mask"].astype(np.float32)[..., None]
        pooled = (output * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)
        vectors = [_l2_normalize(row.astype(float).tolist()) for row in pooled]
        return vectors, "minilm_onnx"
    except Exception:
        return None, "lexical"


def _lexical_vectors(candidates: list[DatasetCandidateORM]) -> list[list[float]]:
    docs = [_tokens(candidate_text(candidate)) for candidate in candidates]
    vocab: dict[str, int] = {}
    for doc in docs:
        for token in sorted(set(doc)):
            if len(vocab) >= 256:
                break
            vocab.setdefault(token, len(vocab))
    if not vocab:
        return [[0.0] for _ in candidates]
    doc_freq = [0] * len(vocab)
    for doc in docs:
        for token in set(doc):
            index = vocab.get(token)
            if index is not None:
                doc_freq[index] += 1
    vectors = []
    total_docs = max(1, len(docs))
    for doc in docs:
        counts: dict[int, int] = {}
        for token in doc:
            index = vocab.get(token)
            if index is not None:
                counts[index] = counts.get(index, 0) + 1
        vector = [0.0] * len(vocab)
        for index, count in counts.items():
            idf = math.log((1 + total_docs) / (1 + doc_freq[index])) + 1
            vector[index] = count * idf
        vectors.append(_l2_normalize(vector))
    return vectors


def _structured_vectors(candidates: list[DatasetCandidateORM]) -> list[list[float]]:
    outputs = []
    for candidate in candidates:
        metrics = candidate.metrics_json or {}
        outcome = 1.0 if metrics.get("outcome") == "Does Not Meet" else 0.0
        outputs.append(
            _l2_normalize(
                [
                    outcome,
                    float(metrics.get("issue_count") or 0),
                    float(metrics.get("driver_count") or 0),
                    math.log1p(float(metrics.get("total_amount_reviewed_dollars") or 0)),
                    math.log1p(float(metrics.get("total_overwrite_dollars") or 0)),
                    math.log1p(float(metrics.get("total_underwrite_dollars") or 0)),
                ]
            )
        )
    return outputs


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", text.lower())


def cluster_vectors(
    vectors: list[list[float]],
    *,
    min_k: int,
    max_k: int,
    seed: int,
) -> tuple[int, list[int], list[float], float | None]:
    matrix = np.asarray(vectors, dtype=float)
    n = matrix.shape[0]
    max_k = min(max_k, n)
    min_k = min(min_k, max_k)
    if max_k <= 1:
        model = _fit_kmeans(matrix, 1, seed)
        return _cluster_model_result(matrix, model, selected_k=1, score=None)
    if n == 2:
        model = _fit_kmeans(matrix, 2, seed)
        return _cluster_model_result(matrix, model, selected_k=2, score=None)

    best: tuple[float | None, int, np.ndarray, np.ndarray] | None = None
    for k in range(max(2, min_k), max_k + 1):
        model = _fit_kmeans(matrix, k, seed)
        labels = model.labels_
        score = _score_silhouette(matrix, labels)
        if best is None or _silhouette_rank(score) > _silhouette_rank(best[0]):
            best = (score, k, labels, model.cluster_centers_)
    if best is None:
        model = _fit_kmeans(matrix, 2, seed)
        best = (_score_silhouette(matrix, model.labels_), 2, model.labels_, model.cluster_centers_)
    score, selected_k, labels, centroids = best
    return _cluster_result(matrix, labels, centroids, selected_k=selected_k, score=score)


def _cluster_model_result(
    vectors: np.ndarray,
    model: KMeans,
    *,
    selected_k: int,
    score: float | None,
) -> tuple[int, list[int], list[float], float | None]:
    return _cluster_result(
        vectors,
        model.labels_,
        model.cluster_centers_,
        selected_k=selected_k,
        score=score,
    )


def _cluster_result(
    vectors: np.ndarray,
    labels: np.ndarray,
    centroids: np.ndarray,
    *,
    selected_k: int,
    score: float | None,
) -> tuple[int, list[int], list[float], float | None]:
    assigned_centroids = centroids[labels]
    distances = np.linalg.norm(vectors - assigned_centroids, axis=1).astype(float).tolist()
    return selected_k, labels.astype(int).tolist(), distances, score


def _fit_kmeans(vectors: np.ndarray, k: int, seed: int) -> KMeans:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        return KMeans(n_clusters=k, random_state=seed, n_init=10).fit(vectors)


def _score_silhouette(vectors: np.ndarray, labels: np.ndarray) -> float | None:
    unique_labels = np.unique(labels)
    if len(unique_labels) < 2 or len(unique_labels) >= len(labels):
        return None
    return float(silhouette_score(vectors, labels, metric="euclidean"))


def _silhouette_rank(score: float | None) -> float:
    return score if score is not None else float("-inf")


def _l2_normalize(vector: list[float]) -> list[float]:
    array = np.asarray(vector, dtype=float)
    norm = np.linalg.norm(array)
    if norm == 0:
        return vector
    return (array / norm).astype(float).tolist()


def sample_candidates(
    candidates: list[DatasetCandidateORM],
    request: DatasetSampleRequest,
) -> set[str]:
    included = [candidate for candidate in candidates if candidate.included]
    if request.mode == "all" or not request.size or request.size >= len(included):
        return {candidate.id for candidate in included}
    rng = random.Random(request.seed)
    size = max(1, request.size)
    if request.mode == "random":
        return {candidate.id for candidate in rng.sample(included, size)}
    if request.mode == "outcome":
        return _proportional_stratified_sample(
            included,
            size,
            lambda item: str((item.metrics_json or {}).get("outcome") or "unknown"),
            rng,
        )
    if request.mode == "stratified_outcome_issues":
        return _round_robin_sample(
            included,
            size,
            lambda item: (
                f"{(item.metrics_json or {}).get('outcome')}:"
                f"{(item.metrics_json or {}).get('issue_count')}"
            ),
            rng,
        )
    if request.mode == "cluster_balanced":
        return _round_robin_sample(
            included,
            size,
            lambda item: str(item.cluster_id if item.cluster_id is not None else "unclustered"),
            rng,
        )
    ordered = sorted(
        included,
        key=lambda item: (
            -(item.cluster_distance or 0),
            -float((item.metrics_json or {}).get("issue_count") or 0),
            item.claim_number,
        ),
    )
    return {candidate.id for candidate in ordered[:size]}


def _proportional_stratified_sample(
    candidates: list[DatasetCandidateORM],
    size: int,
    key_fn: Callable[[DatasetCandidateORM], str],
    rng: random.Random,
) -> set[str]:
    groups: dict[str, list[DatasetCandidateORM]] = {}
    for candidate in candidates:
        groups.setdefault(key_fn(candidate), []).append(candidate)
    for values in groups.values():
        rng.shuffle(values)

    total = max(1, len(candidates))
    quotas = {key: (len(values) / total) * size for key, values in groups.items()}
    counts = {key: min(len(groups[key]), int(math.floor(quota))) for key, quota in quotas.items()}
    remaining = size - sum(counts.values())
    remainder_order = sorted(
        groups,
        key=lambda key: (quotas[key] - math.floor(quotas[key]), len(groups[key]), key),
        reverse=True,
    )
    while remaining > 0 and remainder_order:
        progressed = False
        for key in remainder_order:
            if remaining <= 0:
                break
            if counts[key] >= len(groups[key]):
                continue
            counts[key] += 1
            remaining -= 1
            progressed = True
        if not progressed:
            break

    selected: set[str] = set()
    for key in sorted(groups):
        selected.update(candidate.id for candidate in groups[key][: counts[key]])
    return selected


def _round_robin_sample(
    candidates: list[DatasetCandidateORM],
    size: int,
    key_fn: Callable[[DatasetCandidateORM], str],
    rng: random.Random,
) -> set[str]:
    groups: dict[str, list[DatasetCandidateORM]] = {}
    for candidate in candidates:
        groups.setdefault(key_fn(candidate), []).append(candidate)
    for values in groups.values():
        rng.shuffle(values)
    selected: set[str] = set()
    while len(selected) < size and any(groups.values()):
        for key in sorted(groups):
            if len(selected) >= size:
                break
            if groups[key]:
                selected.add(groups[key].pop().id)
    return selected


def sample_reason(
    candidate: DatasetCandidateORM,
    request: DatasetSampleRequest,
    included: bool,
) -> str:
    if request.mode == "all":
        return "Included by all-candidates sample."
    if included:
        if request.mode == "outcome":
            metrics = candidate.metrics_json or {}
            return f"Included by outcome-proportional sample for {metrics.get('outcome')}."
        if request.mode == "cluster_balanced":
            return f"Included by cluster-balanced sample from cluster {candidate.cluster_id}."
        if request.mode == "stratified_outcome_issues":
            metrics = candidate.metrics_json or {}
            return (
                "Included by outcome/issues stratum "
                f"{metrics.get('outcome')} / {metrics.get('issue_count')} issue(s)."
            )
        if request.mode == "diversity":
            return "Included by diversity ranking."
        return "Included by random sample."
    return f"Excluded by {request.mode} sample."


_candidate_vectors = candidate_vectors
_cluster_vectors = cluster_vectors
_sample_candidates = sample_candidates
_sample_reason = sample_reason

__all__ = [
    "_candidate_vectors",
    "_cluster_vectors",
    "_sample_candidates",
    "_sample_reason",
    "candidate_vectors",
    "cluster_vectors",
    "sample_candidates",
    "sample_reason",
]
