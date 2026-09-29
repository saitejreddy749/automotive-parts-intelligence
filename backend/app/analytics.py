import hashlib
import json
import os
from collections import defaultdict
from time import perf_counter

import numpy as np
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .catalogue import ROOT
from .database import engine
from .matching import CANDIDATE_FLOOR, MODEL_VERSION, description_similarities, normalize_text, score_pair, vector_for
from .models import CanonicalPart, Catalogue, Evaluation, GoldPair, Part, Proposal


def part_dict(part: Part) -> dict:
    return {
        "id": part.id, "supplier": part.supplier, "sku": part.sku, "brand": part.brand,
        "part_number": part.part_number, "description": part.description,
        "category": part.category, "make": part.make, "model": part.model,
        "year_start": part.year_start, "year_end": part.year_end, "engine": part.engine,
        "canonical_id": part.canonical_id,
    }


def proposal_dict(proposal: Proposal, part_map: dict[int, Part]) -> dict:
    return {
        "id": proposal.id, "score": proposal.score, "status": proposal.status,
        "signals": json.loads(proposal.signals_json),
        "left": part_dict(part_map[proposal.left_id]),
        "right": part_dict(part_map[proposal.right_id]),
    }


def overview(session: Session) -> dict:
    def count(model):
        return session.scalar(select(func.count()).select_from(model)) or 0

    return {
        "catalogues": count(Catalogue), "supplier_rows": count(Part),
        "canonical_parts": count(CanonicalPart), "proposals": count(Proposal),
        "pending": session.scalar(select(func.count()).select_from(Proposal).where(Proposal.status == "pending")) or 0,
        "gold_pairs": count(GoldPair), "evaluations": count(Evaluation),
        "vector_index": "pgvector" if engine.dialect.name == "postgresql" else "local hashing vectors",
        "raw_storage": "Azure Blob" if os.getenv("AZURE_STORAGE_CONNECTION_STRING") else "local files",
        "ai_enabled": all(os.getenv(name) for name in (
            "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION"
        )),
        "model_version": MODEL_VERSION,
    }


def catalogue_list(session: Session) -> list[dict]:
    return [{
        "id": c.id, "filename": c.filename, "rows": c.record_count,
        "invalid": c.invalid_count, "sha256": c.sha256[:12],
        "uploaded_at": c.uploaded_at, "storage": c.storage_ref.split("://")[0],
    } for c in session.scalars(select(Catalogue).order_by(Catalogue.id.desc()))]


def canonical_search(session: Session, q: str = "", limit: int = 50) -> list[dict]:
    parts = session.scalars(select(Part).order_by(Part.id)).all()
    groups = defaultdict(list)
    for part in parts:
        groups[part.canonical_id].append(part_dict(part))
    if q:
        needle = normalize_text(q)
        groups = {cid: rows for cid, rows in groups.items() if any(
            needle in normalize_text(f"{row['brand']} {row['part_number']} {row['description']} {row['category']} {row['sku']}")
            or needle.replace(" ", "") in "".join(ch for ch in row["part_number"].casefold() if ch.isalnum())
            for row in rows
        )}
    return [{"canonical_id": cid, "source_count": len(rows), "sources": rows}
            for cid, rows in list(groups.items())[:limit]]


def fitment_search(session: Session, make: str, model: str, year: int, engine_name: str = "") -> list[dict]:
    result = defaultdict(list)
    for part in session.scalars(select(Part).where(Part.year_start <= year, Part.year_end >= year)):
        if normalize_text(part.make) != normalize_text(make) or normalize_text(part.model) != normalize_text(model):
            continue
        if engine_name and part.engine and normalize_text(part.engine) != normalize_text(engine_name):
            continue
        status = "declared" if part.engine and engine_name and normalize_text(part.engine) == normalize_text(engine_name) else "engine_unverified"
        result[part.canonical_id].append({**part_dict(part), "status": status})
    return [{"canonical_id": cid, "sources": rows,
             "status": "declared" if any(r["status"] == "declared" for r in rows) else "engine_unverified"}
            for cid, rows in result.items()]


def similar_parts(session: Session, part_id: int, limit: int = 5) -> list[dict]:
    source = session.get(Part, part_id)
    if source is None:
        raise LookupError("Part not found")
    candidates = [p for p in session.scalars(select(Part))
                  if p.id != source.id and p.supplier.casefold() != source.supplier.casefold()
                  and p.norm_brand == source.norm_brand and normalize_text(p.category) == normalize_text(source.category)]
    if engine.dialect.name == "postgresql":
        values = ",".join(f"{n:.7f}" for n in vector_for(source))
        ids = [p.id for p in candidates]
        if not ids:
            return []
        # Parameterized vector value; candidate IDs come from the database.
        rows = session.execute(text("""SELECT part_id, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM part_vectors WHERE part_id = ANY(:ids)
            ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :limit"""),
            {"embedding": f"[{values}]", "ids": ids, "limit": limit}).all()
        scores = [(part_id, float(sim)) for part_id, sim in rows]
    else:
        source_vector = np.asarray(vector_for(source))
        scores = [(p.id, float(np.dot(source_vector, vector_for(p)))) for p in candidates]
        scores.sort(key=lambda item: (-item[1], item[0]))
    by_id = {p.id: p for p in candidates}
    return [{"part": part_dict(by_id[id_]), "similarity": round(score, 4)}
            for id_, score in scores[:limit]]


def evaluate(session: Session, threshold: float) -> Evaluation:
    labels = session.scalars(select(GoldPair).order_by(GoldPair.id)).all()
    if not labels:
        raise LookupError("No labeled pairs. Load the demo dataset to run evaluation.")
    parts = session.scalars(select(Part).order_by(Part.id)).all()
    index = {part.id: i for i, part in enumerate(parts)}
    started = perf_counter()
    similarities, _ = description_similarities(parts)
    positives = set()
    scored = []
    errors = []
    scoring_failures = 0
    for pair in labels:
        left, right = parts[index[pair.left_id]], parts[index[pair.right_id]]
        try:
            score, signals = score_pair(left, right, similarities[index[left.id], index[right.id]])
        except (ValueError, TypeError, IndexError, FloatingPointError) as exc:
            scoring_failures += 1
            score, signals = 0.0, {"scoring_error": type(exc).__name__}
        prediction = score >= threshold
        if pair.label:
            positives.add((left.id, right.id))
        if prediction != bool(pair.label):
            errors.append({
                "left": part_dict(left), "right": part_dict(right),
                "expected": bool(pair.label), "predicted": prediction,
                "score": score, "signals": signals,
            })
        scored.append((pair.label, prediction))
    total_ms = (perf_counter() - started) * 1000
    tp = sum(label and predicted for label, predicted in scored)
    fp = sum(not label and predicted for label, predicted in scored)
    fn = sum(label and not predicted for label, predicted in scored)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    # Ranking quality on positive demo queries, using all cross-supplier rows.
    per_left = defaultdict(set)
    for left_id, right_id in positives:
        per_left[left_id].add(right_id)
    top1 = top3 = 0
    for left_id, target_ids in per_left.items():
        left = parts[index[left_id]]
        ranked = []
        for right in parts:
            if right.supplier == left.supplier:
                continue
            score, _ = score_pair(left, right, similarities[index[left.id], index[right.id]])
            if score >= CANDIDATE_FLOOR:
                ranked.append((score, right.id))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        ids = [part_id for _, part_id in ranked]
        top1 += bool(ids and ids[0] in target_ids)
        top3 += any(part_id in target_ids for part_id in ids[:3])

    digest = hashlib.sha256(b"".join((ROOT / "data" / name).read_bytes() for name in
        ("supplier_north.csv", "supplier_south.csv", "gold_pairs.csv"))).hexdigest()[:12]
    record = Evaluation(
        threshold=threshold, label_count=len(labels), precision=precision, recall=recall,
        f1=f1, precision_at_1=top1 / len(per_left) if per_left else 0,
        recall_at_3=top3 / len(per_left) if per_left else 0,
        avg_latency_ms=total_ms / len(labels), failure_rate=scoring_failures / len(labels),
        false_positives=fp, false_negatives=fn, data_version=digest,
        model_version=MODEL_VERSION, errors_json=json.dumps(errors),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def evaluation_dict(item: Evaluation, with_errors: bool = False) -> dict:
    result = {key: getattr(item, key) for key in (
        "id", "run_at", "threshold", "label_count", "precision", "recall", "f1",
        "precision_at_1", "recall_at_3", "avg_latency_ms", "failure_rate",
        "false_positives", "false_negatives", "data_version", "model_version",
    )}
    if with_errors:
        result["errors"] = json.loads(item.errors_json)
    return result
