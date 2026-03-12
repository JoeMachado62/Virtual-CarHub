from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, distinct, select
from sqlalchemy.orm import Session

from app.models.entities import Vehicle, VehicleTaxonomyCache

MIN_TAXONOMY_YEAR = 2015


def _normalize_term(value: object) -> str:
    return str(value or "").strip()


def _extract_terms(payload: object, field_name: str) -> list[str]:
    candidates: list[object] = []
    if isinstance(payload, dict):
        for key in ("terms", "data", "results", "items", field_name):
            value = payload.get(key)
            if isinstance(value, list):
                candidates = value
                break
    elif isinstance(payload, list):
        candidates = payload

    terms: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if isinstance(candidate, dict):
            value = candidate.get("item") or candidate.get("value") or candidate.get(field_name)
        else:
            value = candidate
        text = _normalize_term(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        terms.append(text)
    return sorted(terms, key=str.casefold)


def _term_buckets(values: list[str | int]) -> list[dict[str, int | str]]:
    return [{"item": str(value), "count": 0} for value in values if str(value).strip()]


def _taxonomy_lookup_rows_from_cache(
    db: Session,
    *,
    min_year: int | None,
    max_year: int | None,
) -> list[tuple[int, str, str, str]]:
    stmt = select(
        VehicleTaxonomyCache.year,
        VehicleTaxonomyCache.make,
        VehicleTaxonomyCache.model,
        VehicleTaxonomyCache.trim,
    ).where(VehicleTaxonomyCache.active.is_(True))
    if min_year is not None:
        stmt = stmt.where(VehicleTaxonomyCache.year >= min_year)
    if max_year is not None:
        stmt = stmt.where(VehicleTaxonomyCache.year <= max_year)
    return list(db.execute(stmt).all())


def _taxonomy_lookup_rows_from_inventory(
    db: Session,
    *,
    min_year: int | None,
    max_year: int | None,
) -> list[tuple[int, str, str, str]]:
    stmt = select(Vehicle).where(Vehicle.available.is_(True))
    if min_year is not None:
        stmt = stmt.where(Vehicle.year >= min_year)
    if max_year is not None:
        stmt = stmt.where(Vehicle.year <= max_year)
    rows = db.scalars(stmt).all()
    return [
        (row.year, row.make or "", row.model or "", row.trim or "")
        for row in rows
        if row.year and _normalize_term(row.make) and _normalize_term(row.model)
    ]


def _build_lookup(rows: list[tuple[int, str, str, str]]) -> dict[str, dict[str, list[str]]]:
    models_by_make: dict[str, set[str]] = {}
    trims_by_make_model: dict[str, set[str]] = {}

    for _year, make, model, trim in rows:
        normalized_make = _normalize_term(make)
        normalized_model = _normalize_term(model)
        normalized_trim = _normalize_term(trim)
        if not normalized_make or not normalized_model:
            continue
        models_by_make.setdefault(normalized_make, set()).add(normalized_model)
        if normalized_trim:
            key = f"{normalized_make}|||{normalized_model}"
            trims_by_make_model.setdefault(key, set()).add(normalized_trim)

    return {
        "models_by_make": {
            make: sorted(values, key=str.casefold)
            for make, values in sorted(models_by_make.items(), key=lambda item: item[0].casefold())
        },
        "trims_by_make_model": {
            key: sorted(values, key=str.casefold)
            for key, values in sorted(trims_by_make_model.items(), key=lambda item: item[0].casefold())
        },
    }


@dataclass(slots=True)
class InventoryTaxonomySyncReport:
    start_year: int
    end_year: int
    deleted: int
    inserted: int
    request_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "start_year": self.start_year,
            "end_year": self.end_year,
            "deleted": self.deleted,
            "inserted": self.inserted,
            "request_count": self.request_count,
        }


def sync_marketcheck_taxonomy_cache(
    db: Session,
    *,
    client: object,
    start_year: int = MIN_TAXONOMY_YEAR,
    end_year: int,
) -> InventoryTaxonomySyncReport:
    get_terms = getattr(client, "get_terms", None)
    if not callable(get_terms):
        raise ValueError("MarketCheck client does not support taxonomy terms")

    normalized_start = max(start_year, MIN_TAXONOMY_YEAR)
    normalized_end = max(normalized_start, end_year)
    now = datetime.now(UTC)
    request_count = 0
    rows: set[tuple[int, str, str, str]] = set()

    for year in range(normalized_start, normalized_end + 1):
        makes = _extract_terms(get_terms("make", {"year": year}), "make")
        request_count += 1
        for make in makes:
            models = _extract_terms(get_terms("model", {"year": year, "make": make}), "model")
            request_count += 1
            for model in models:
                trims = _extract_terms(get_terms("trim", {"year": year, "make": make, "model": model}), "trim")
                request_count += 1
                if trims:
                    for trim in trims:
                        rows.add((year, make, model, trim))
                else:
                    rows.add((year, make, model, ""))

    deleted = db.execute(
        delete(VehicleTaxonomyCache).where(
            VehicleTaxonomyCache.year >= normalized_start,
            VehicleTaxonomyCache.year <= normalized_end,
        )
    ).rowcount or 0

    if rows:
        db.bulk_save_objects(
            [
                VehicleTaxonomyCache(
                    year=year,
                    make=make,
                    model=model,
                    trim=trim,
                    source="marketcheck",
                    active=True,
                    last_synced_at=now,
                )
                for year, make, model, trim in sorted(rows)
            ]
        )

    return InventoryTaxonomySyncReport(
        start_year=normalized_start,
        end_year=normalized_end,
        deleted=deleted,
        inserted=len(rows),
        request_count=request_count,
    )


def get_inventory_taxonomy_facets(
    db: Session,
    *,
    min_year: int | None,
    max_year: int | None,
    make: str | None,
    model: str | None,
) -> dict[str, object]:
    taxonomy_count = db.scalar(select(VehicleTaxonomyCache.id).limit(1))
    if taxonomy_count:
        return _taxonomy_from_cache(db, min_year=min_year, max_year=max_year, make=make, model=model)
    return _taxonomy_from_inventory(db, min_year=min_year, max_year=max_year, make=make, model=model)


def _taxonomy_from_cache(
    db: Session,
    *,
    min_year: int | None,
    max_year: int | None,
    make: str | None,
    model: str | None,
) -> dict[str, object]:
    year_stmt = select(distinct(VehicleTaxonomyCache.year)).where(VehicleTaxonomyCache.active.is_(True))
    if min_year is not None:
        year_stmt = year_stmt.where(VehicleTaxonomyCache.year >= min_year)
    if max_year is not None:
        year_stmt = year_stmt.where(VehicleTaxonomyCache.year <= max_year)
    years = sorted(db.scalars(year_stmt).all(), reverse=True)

    make_stmt = select(distinct(VehicleTaxonomyCache.make)).where(VehicleTaxonomyCache.active.is_(True))
    if min_year is not None:
        make_stmt = make_stmt.where(VehicleTaxonomyCache.year >= min_year)
    if max_year is not None:
        make_stmt = make_stmt.where(VehicleTaxonomyCache.year <= max_year)
    makes = sorted([value for value in db.scalars(make_stmt).all() if _normalize_term(value)], key=str.casefold)

    models: list[str] = []
    if _normalize_term(make):
        model_stmt = select(distinct(VehicleTaxonomyCache.model)).where(
            VehicleTaxonomyCache.active.is_(True),
            VehicleTaxonomyCache.make == _normalize_term(make),
        )
        if min_year is not None:
            model_stmt = model_stmt.where(VehicleTaxonomyCache.year >= min_year)
        if max_year is not None:
            model_stmt = model_stmt.where(VehicleTaxonomyCache.year <= max_year)
        models = sorted([value for value in db.scalars(model_stmt).all() if _normalize_term(value)], key=str.casefold)

    trims: list[str] = []
    if _normalize_term(make) and _normalize_term(model):
        trim_stmt = select(distinct(VehicleTaxonomyCache.trim)).where(
            VehicleTaxonomyCache.active.is_(True),
            VehicleTaxonomyCache.make == _normalize_term(make),
            VehicleTaxonomyCache.model == _normalize_term(model),
            VehicleTaxonomyCache.trim != "",
        )
        if min_year is not None:
            trim_stmt = trim_stmt.where(VehicleTaxonomyCache.year >= min_year)
        if max_year is not None:
            trim_stmt = trim_stmt.where(VehicleTaxonomyCache.year <= max_year)
        trims = sorted([value for value in db.scalars(trim_stmt).all() if _normalize_term(value)], key=str.casefold)

    return {
        "source": "taxonomy_cache",
        "years": _term_buckets(years),
        "make": _term_buckets(makes),
        "model": _term_buckets(models),
        "trim": _term_buckets(trims),
        "lookup": _build_lookup(
            _taxonomy_lookup_rows_from_cache(
                db,
                min_year=min_year,
                max_year=max_year,
            )
        ),
    }


def _taxonomy_from_inventory(
    db: Session,
    *,
    min_year: int | None,
    max_year: int | None,
    make: str | None,
    model: str | None,
) -> dict[str, object]:
    stmt = select(Vehicle).where(Vehicle.available.is_(True))
    if min_year is not None:
        stmt = stmt.where(Vehicle.year >= min_year)
    if max_year is not None:
        stmt = stmt.where(Vehicle.year <= max_year)

    rows = db.scalars(stmt).all()
    years = sorted({row.year for row in rows if row.year}, reverse=True)
    makes = sorted({row.make for row in rows if _normalize_term(row.make)}, key=str.casefold)

    normalized_make = _normalize_term(make)
    if normalized_make:
        rows = [row for row in rows if _normalize_term(row.make).casefold() == normalized_make.casefold()]
    models = sorted({row.model for row in rows if _normalize_term(row.model)}, key=str.casefold)

    normalized_model = _normalize_term(model)
    if normalized_make and normalized_model:
        rows = [
            row
            for row in rows
            if _normalize_term(row.model).casefold() == normalized_model.casefold()
        ]
        trims = sorted({row.trim for row in rows if _normalize_term(row.trim)}, key=str.casefold)
    else:
        trims = []

    return {
        "source": "inventory_fallback",
        "years": _term_buckets(years),
        "make": _term_buckets(makes),
        "model": _term_buckets(models if normalized_make else []),
        "trim": _term_buckets(trims),
        "lookup": _build_lookup(
            _taxonomy_lookup_rows_from_inventory(
                db,
                min_year=min_year,
                max_year=max_year,
            )
        ),
    }
