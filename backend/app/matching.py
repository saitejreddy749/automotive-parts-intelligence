"""Explainable duplicate suggestions. Vehicle fitment is never inferred here."""

import re
from time import perf_counter

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


MODEL_VERSION = "rules-tfidf-v1"
MODEL_VERSIONS = {
    MODEL_VERSION: "Part number, description similarity, and declared fitment overlap",
    "rules-tfidf-v2": "The same score with penalties for conflicting vehicle or engine declarations",
}
CANDIDATE_FLOOR = 0.55
hashing = HashingVectorizer(
    analyzer="char_wb", ngram_range=(3, 5), n_features=64,
    alternate_sign=False, norm="l2", lowercase=True,
)


def normalize_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def normalize_number(value: str) -> str:
    return "".join(re.findall(r"[A-Z0-9]+", value.upper()))


def vector_for(part) -> list[float]:
    text = f"{part.norm_brand} {part.norm_number} {part.norm_description}"
    return hashing.transform([text]).toarray()[0].astype(float).tolist()


def description_similarities(parts) -> tuple[np.ndarray, float]:
    started = perf_counter()
    descriptions = [p.norm_description or "empty" for p in parts]
    if not descriptions:
        return np.zeros((0, 0)), 0.0
    matrix = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit_transform(descriptions)
    return cosine_similarity(matrix), (perf_counter() - started) * 1000


def fitment_overlap(left, right) -> bool:
    same_vehicle = (
        normalize_text(left.make) == normalize_text(right.make)
        and normalize_text(left.model) == normalize_text(right.model)
    )
    engine_agrees = not left.engine or not right.engine or normalize_text(left.engine) == normalize_text(right.engine)
    years_overlap = left.year_start <= right.year_end and right.year_start <= left.year_end
    return same_vehicle and engine_agrees and years_overlap


def score_pair(left, right, description_similarity: float, model_version: str = MODEL_VERSION) -> tuple[float, dict]:
    if model_version not in MODEL_VERSIONS:
        raise ValueError("Unknown matching model")
    same_brand = left.norm_brand == right.norm_brand
    same_category = normalize_text(left.category) == normalize_text(right.category)
    exact_number = bool(left.norm_number) and left.norm_number == right.norm_number
    fitment = fitment_overlap(left, right)
    vehicle_conflict = (normalize_text(left.make) != normalize_text(right.make)
                        or normalize_text(left.model) != normalize_text(right.model))
    engine_conflict = bool(left.engine and right.engine) and normalize_text(left.engine) != normalize_text(right.engine)
    signals = {
        "brand_agrees": same_brand,
        "category_agrees": same_category,
        "exact_part_number": exact_number,
        "description_similarity": round(float(description_similarity), 4),
        "declared_fitment_overlaps": fitment,
        "vehicle_conflict": vehicle_conflict,
        "engine_conflict": engine_conflict,
    }
    if not same_brand or not same_category:
        return 0.0, signals
    if exact_number:
        score = 0.82 + 0.15 * description_similarity + 0.03 * fitment
    else:
        score = 0.54 * description_similarity + 0.18 * fitment
    if model_version == "rules-tfidf-v2":
        score -= 0.5 * vehicle_conflict + 0.25 * engine_conflict
    return round(max(0.0, min(float(score), 1.0)), 4), signals
