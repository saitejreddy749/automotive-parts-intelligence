from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Catalogue(Base):
    __tablename__ = "catalogues"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    storage_ref: Mapped[str] = mapped_column(String(512))
    record_count: Mapped[int] = mapped_column(Integer)
    invalid_count: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CanonicalPart(Base):
    __tablename__ = "canonical_parts"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Part(Base):
    __tablename__ = "parts"
    __table_args__ = (UniqueConstraint("supplier", "sku", name="uq_supplier_sku"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    catalogue_id: Mapped[int] = mapped_column(ForeignKey("catalogues.id"), index=True)
    canonical_id: Mapped[int] = mapped_column(ForeignKey("canonical_parts.id"), index=True)
    supplier: Mapped[str] = mapped_column(String(100))
    sku: Mapped[str] = mapped_column(String(100))
    brand: Mapped[str] = mapped_column(String(100))
    part_number: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(80))
    make: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80))
    year_start: Mapped[int] = mapped_column(Integer)
    year_end: Mapped[int] = mapped_column(Integer)
    engine: Mapped[str] = mapped_column(String(80), default="")
    norm_brand: Mapped[str] = mapped_column(String(100), index=True)
    norm_number: Mapped[str] = mapped_column(String(100), index=True)
    norm_description: Mapped[str] = mapped_column(String(500))


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (UniqueConstraint("left_id", "right_id", name="uq_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    left_id: Mapped[int] = mapped_column(ForeignKey("parts.id"), index=True)
    right_id: Mapped[int] = mapped_column(ForeignKey("parts.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    signals_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GoldPair(Base):
    __tablename__ = "gold_pairs"
    __table_args__ = (UniqueConstraint("left_id", "right_id", name="uq_gold_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    left_id: Mapped[int] = mapped_column(ForeignKey("parts.id"))
    right_id: Mapped[int] = mapped_column(ForeignKey("parts.id"))
    label: Mapped[int] = mapped_column(Integer)


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    threshold: Mapped[float] = mapped_column(Float)
    label_count: Mapped[int] = mapped_column(Integer)
    precision: Mapped[float] = mapped_column(Float)
    recall: Mapped[float] = mapped_column(Float)
    f1: Mapped[float] = mapped_column(Float)
    precision_at_1: Mapped[float] = mapped_column(Float)
    recall_at_3: Mapped[float] = mapped_column(Float)
    avg_latency_ms: Mapped[float] = mapped_column(Float)
    failure_rate: Mapped[float] = mapped_column(Float)
    false_positives: Mapped[int] = mapped_column(Integer)
    false_negatives: Mapped[int] = mapped_column(Integer)
    data_version: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(40))
    errors_json: Mapped[str] = mapped_column(Text)
