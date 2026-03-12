from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.base import Base
from app.models import *  # noqa: F401,F403


def _table_names(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _chunks(rows: list[dict], size: int):
    for idx in range(0, len(rows), size):
        yield rows[idx : idx + size]


def migrate(sqlite_path: Path, postgres_url: str, truncate_target: bool, batch_size: int) -> None:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite DB file not found: {sqlite_path}")
    if not postgres_url.startswith("postgresql"):
        raise ValueError("Target URL must be a PostgreSQL URL")

    source_engine = create_engine(f"sqlite:///{sqlite_path}", future=True)
    target_engine = create_engine(postgres_url, future=True)

    Base.metadata.create_all(bind=target_engine)

    source_tables = _table_names(source_engine)
    ordered_tables = list(Base.metadata.sorted_tables)

    with source_engine.connect() as source_conn, target_engine.begin() as target_conn:
        if truncate_target:
            for table in reversed(ordered_tables):
                target_conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
            print("Truncated target tables.")

        for table in ordered_tables:
            if table.name not in source_tables:
                print(f"[SKIP] {table.name}: not present in SQLite source")
                continue

            rows = [dict(row) for row in source_conn.execute(select(table)).mappings().all()]
            if not rows:
                print(f"[OK] {table.name}: 0 rows")
                continue

            pk_columns = [column.name for column in table.primary_key.columns]
            inserted_count = 0
            for batch in _chunks(rows, batch_size):
                stmt = pg_insert(table).values(batch)
                if pk_columns:
                    update_set = {col.name: stmt.excluded[col.name] for col in table.columns if col.name not in pk_columns}
                    if update_set:
                        stmt = stmt.on_conflict_do_update(index_elements=pk_columns, set_=update_set)
                    else:
                        stmt = stmt.on_conflict_do_nothing(index_elements=pk_columns)
                target_conn.execute(stmt)
                inserted_count += len(batch)

            print(f"[OK] {table.name}: {inserted_count} rows migrated")

    source_engine.dispose()
    target_engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate existing SQLite VirtualCarHub DB to PostgreSQL.")
    parser.add_argument(
        "--sqlite-path",
        default="virtual_carhub.db",
        help="Path to SQLite DB file (default: ./virtual_carhub.db from backend dir).",
    )
    parser.add_argument(
        "--postgres-url",
        default=settings.database_url,
        help="Target PostgreSQL URL (defaults to DATABASE_URL).",
    )
    parser.add_argument(
        "--truncate-target",
        action="store_true",
        help="Truncate target tables before import.",
    )
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch insert size (default: 1000).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sqlite_path = Path(args.sqlite_path).expanduser().resolve()
    migrate(
        sqlite_path=sqlite_path,
        postgres_url=args.postgres_url,
        truncate_target=args.truncate_target,
        batch_size=max(1, args.batch_size),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
