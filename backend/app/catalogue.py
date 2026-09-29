import csv
import hashlib
import io
import json
import os
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .database import engine
from .matching import CANDIDATE_FLOOR, description_similarities, normalize_number, normalize_text, score_pair, vector_for
from .models import CanonicalPart, Catalogue, GoldPair, Part, Proposal


ROOT = Path(__file__).resolve().parents[2]
REQUIRED = {"supplier", "sku", "brand", "part_number", "description", "category", "make", "model", "year_start", "year_end"}
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 500
MAX_TOTAL_PARTS = 1500


class CatalogueError(ValueError):
    pass


def init_vector_store():
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("""CREATE TABLE IF NOT EXISTS part_vectors (
            part_id INTEGER PRIMARY KEY REFERENCES parts(id) ON DELETE CASCADE,
            embedding vector(64) NOT NULL
        )"""))
        connection.execute(text("""CREATE INDEX IF NOT EXISTS part_vectors_cosine_idx
            ON part_vectors USING hnsw (embedding vector_cosine_ops)"""))


def parse_csv(data: bytes, existing_keys: set[tuple[str, str]]) -> tuple[list[dict], list[dict]]:
    if not data or len(data) > MAX_BYTES:
        raise CatalogueError("CSV must be nonempty and at most 2 MB")
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CatalogueError("CSV must use UTF-8 encoding") from exc
    reader = csv.DictReader(io.StringIO(content, newline=""))
    if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
        raise CatalogueError("Missing columns: " + ", ".join(sorted(REQUIRED - set(reader.fieldnames or []))))
    records, errors = [], []
    seen = set(existing_keys)
    for line, item in enumerate(reader, start=2):
        if line > MAX_ROWS + 1:
            raise CatalogueError(f"A catalogue can contain at most {MAX_ROWS} rows")
        try:
            if None in item or any(value is None for value in item.values()):
                raise ValueError("Malformed CSV row")
            row = {key: (item.get(key) or "").strip() for key in REQUIRED | {"engine"}}
            if any(not row[key] for key in REQUIRED):
                raise ValueError("Required values cannot be blank")
            if any(len(row[key]) > cap for key, cap in {
                "supplier": 100, "sku": 100, "brand": 100, "part_number": 100,
                "description": 500, "category": 80, "make": 80, "model": 80, "engine": 80,
            }.items()):
                raise ValueError("A text field exceeds its allowed length")
            row["year_start"], row["year_end"] = int(row["year_start"]), int(row["year_end"])
            if not 1900 <= row["year_start"] <= row["year_end"] <= 2100:
                raise ValueError("Invalid year range")
            key = (row["supplier"].casefold(), row["sku"].casefold())
            if key in seen:
                raise ValueError("Duplicate supplier and SKU")
            seen.add(key)
            records.append(row)
        except ValueError as exc:
            errors.append({"line": line, "reason": str(exc)})
    if not records:
        raise CatalogueError("No valid rows in catalogue")
    return records, errors


def save_source(data: bytes, digest: str, filename: str) -> str:
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if connection_string:
        from azure.storage.blob import BlobServiceClient

        container = os.getenv("AZURE_STORAGE_CONTAINER", "supplier-catalogues")
        client = BlobServiceClient.from_connection_string(connection_string)
        blob_name = digest + ".csv"
        client.get_blob_client(container=container, blob=blob_name).upload_blob(data, overwrite=True)
        return f"azure://{container}/{blob_name}"
    directory = Path(os.getenv("STORAGE_DIR", "./uploads"))
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{digest}.csv"
    destination.write_bytes(data)
    return f"local://{destination.name}"


def store_vectors(session: Session, parts: list[Part]):
    if engine.dialect.name != "postgresql":
        return
    for part in parts:
        values = ",".join(f"{value:.7f}" for value in vector_for(part))
        session.execute(text("""INSERT INTO part_vectors (part_id, embedding)
            VALUES (:part_id, CAST(:embedding AS vector))
            ON CONFLICT (part_id) DO UPDATE SET embedding = EXCLUDED.embedding"""),
            {"part_id": part.id, "embedding": f"[{values}]"})


def ingest_csv(session: Session, data: bytes, filename: str) -> dict:
    if not filename.lower().endswith(".csv"):
        raise CatalogueError("Upload a .csv file")
    digest = hashlib.sha256(data).hexdigest()
    if session.scalar(select(Catalogue.id).where(Catalogue.sha256 == digest)):
        raise CatalogueError("This exact catalogue has already been uploaded")
    existing = session.scalars(select(Part)).all()
    records, errors = parse_csv(data, {(p.supplier.casefold(), p.sku.casefold()) for p in existing})
    if len(existing) + len(records) > MAX_TOTAL_PARTS:
        raise CatalogueError(f"Demo limit is {MAX_TOTAL_PARTS} total rows")
    storage_ref = save_source(data, digest, filename)
    catalogue = Catalogue(
        filename=Path(filename).name[:255], sha256=digest, storage_ref=storage_ref,
        record_count=len(records), invalid_count=len(errors),
    )
    session.add(catalogue)
    session.flush()
    added = []
    for row in records:
        canonical = CanonicalPart()
        session.add(canonical)
        session.flush()
        part = Part(
            catalogue_id=catalogue.id, canonical_id=canonical.id, **row,
            norm_brand=normalize_text(row["brand"]),
            norm_number=normalize_number(row["part_number"]),
            norm_description=normalize_text(row["description"]),
        )
        session.add(part)
        added.append(part)
    session.flush()
    store_vectors(session, added)
    proposal_count = create_proposals(session, existing + added, {p.id for p in added})
    return {
        "catalogue_id": catalogue.id, "accepted": len(added), "invalid": errors,
        "new_proposals": proposal_count, "sha256": digest,
    }


def create_proposals(session: Session, parts: list[Part], new_ids: set[int]) -> int:
    similarities, _ = description_similarities(parts)
    count = 0
    for i, left in enumerate(parts):
        for j in range(i + 1, len(parts)):
            right = parts[j]
            if right.id not in new_ids and left.id not in new_ids:
                continue
            if left.supplier.casefold() == right.supplier.casefold():
                continue
            score, signals = score_pair(left, right, similarities[i, j])
            if score < CANDIDATE_FLOOR:
                continue
            a, b = sorted((left.id, right.id))
            session.add(Proposal(left_id=a, right_id=b, score=score, signals_json=json.dumps(signals)))
            count += 1
    session.flush()
    return count


def seed_demo(session: Session) -> bool:
    if session.scalar(select(Catalogue.id).limit(1)):
        return False
    for filename in ("supplier_north.csv", "supplier_south.csv"):
        ingest_csv(session, (ROOT / "data" / filename).read_bytes(), filename)
    parts = {(part.supplier, part.sku): part.id for part in session.scalars(select(Part)).all()}
    with (ROOT / "data" / "gold_pairs.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            a = parts[("North Supply", row["north_sku"])]
            b = parts[("South Supply", row["south_sku"])]
            session.add(GoldPair(left_id=min(a, b), right_id=max(a, b), label=int(row["label"])))
    session.commit()
    return True
