"""Typed, read-only views over all release tables for downstream builders."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import duckdb


_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_TYPES = {"VARCHAR", "BIGINT", "DOUBLE", "BOOLEAN", "DATE", "TIMESTAMP"}
_LOGICAL_TYPES = {"string": "VARCHAR", "enum": "VARCHAR", "date": "DATE"}

# These fields describe an event or completed snapshot that was observable
# before a later prediction time. Current-state account/case tables are omitted.
HISTORICAL_SOURCES = {
    "contact_history": ("contact_ts_local", "TIMESTAMP"),
    "transactions": ("posting_date", "DATE"),
    "account_monthly_snapshot": ("month_end_date", "DATE"),
    "bureau_history": ("pull_date", "DATE"),
}


def _quote_path(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def register_clean_views(con: duckdb.DuckDBPyConnection, dataset_root: Path) -> list[str]:
    """Register one typed ``clean_*`` view per table in the release schema."""
    root = dataset_root.resolve()
    schema = json.loads((root / "schema" / "schema.json").read_text(encoding="utf-8"))
    created = []
    for table, spec in schema.items():
        if not _NAME.fullmatch(table):
            raise ValueError(f"Unsafe table name in schema: {table}")
        path = root / spec["path"]
        if spec["format"] == "csv":
            if not path.is_file():
                raise FileNotFoundError(path)
            source = f"read_csv({_quote_path(path)}, header=true, all_varchar=true)"
        elif spec["format"].startswith("parquet"):
            if not path.is_dir():
                raise FileNotFoundError(path)
            source = f"read_parquet({_quote_path(path / '*' / '*.parquet')}, hive_partitioning=true)"
        else:
            raise ValueError(f"Unsupported release format: {spec['format']}")
        columns = []
        for column in spec["columns"]:
            name = column["name"]
            physical_type = column.get("physical_type", _LOGICAL_TYPES.get(column["type"], "")).upper()
            if not _NAME.fullmatch(name) or physical_type not in _TYPES:
                raise ValueError(f"Unsafe schema column: {table}.{name} {physical_type}")
            quoted = f'"{name}"'
            if table == "account_monthly_snapshot" and name == "month_end_date":
                expression = "CAST(try_strptime(month_end_date, " \
                    "['%Y-%m-%d', '%d/%m/%Y', '%Y%m%d']) AS DATE)"
            elif physical_type == "VARCHAR":
                expression = quoted
            else:
                expression = f"try_cast({quoted} AS {physical_type})"
            columns.append(f"{expression} AS {quoted}")
        con.execute(f"CREATE OR REPLACE VIEW clean_{table} AS "
                    f"SELECT {', '.join(columns)} FROM {source}")
        created.append(f"clean_{table}")
    return created


def as_of_sql(table: str) -> str:
    """Parameterized query for rows strictly before a prediction timestamp.

    Bind the prediction timestamp as the sole parameter. Day-grain sources
    exclude the cutoff day because their intraday availability is unknown.
    Only approved historical tables are accepted; current snapshots and
    outcome-bearing promise rows require feature-specific treatment.
    """
    if table not in HISTORICAL_SOURCES:
        raise ValueError(f"No safe historical view for {table}")
    date_column, date_type = HISTORICAL_SOURCES[table]
    return f"SELECT * FROM clean_{table} WHERE {date_column} < CAST(? AS {date_type})"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path,
                        default=Path("maple_data/maple_collections_release"))
    parser.add_argument("--database", type=Path,
                        default=Path("local_artifacts/c360/clean_views.duckdb"))
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(args.database))
    try:
        views = register_clean_views(con, args.data_dir)
        print(f"Registered {len(views)} typed views in {args.database}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
