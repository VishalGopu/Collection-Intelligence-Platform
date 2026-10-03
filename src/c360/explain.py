"""Explain published identity links without displaying raw personal attributes.

From the repository root:
  .venv/Scripts/python src/c360/explain.py G-...
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def _sql_path(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def explain_customer(
    golden_id: str, output_dir: Path = Path("local_artifacts/c360")
) -> dict[str, object]:
    """Return a Streamlit-ready identity summary from published C360 files."""
    output_dir = Path(output_dir)
    required = (
        "identity_crosswalk.parquet", "silver_customers.parquet",
        "silver_source_profiles.parquet",
    )
    for name in required:
        if not (output_dir / name).is_file():
            raise FileNotFoundError(f"Missing {output_dir / name}; run src/c360/build.py")
    con = duckdb.connect(":memory:")
    try:
        rows = con.execute(f"""
            WITH linked AS (
              SELECT source_system, source_customer_id, golden_customer_id,
                     match_method, match_confidence, link_status
              FROM read_parquet({_sql_path(output_dir / 'identity_crosswalk.parquet')})
              WHERE golden_customer_id = ? AND link_status = 'linked'
            ), evidence AS (
              SELECT x.source_system, x.source_customer_id,
                bool_or(s.dob IS NOT NULL AND s.dob = c.dob) AS dob_match,
                bool_or(s.postal IS NOT NULL AND s.postal = c.postal) AS postal_match,
                bool_or(s.phone IS NOT NULL AND s.phone = c.phone) AS phone_match,
                bool_or(c.surname <> '' AND
                  contains(' ' || s.name || ' ', ' ' || c.surname || ' ')) AS surname_match
              FROM linked x
              JOIN read_parquet({_sql_path(output_dir / 'silver_source_profiles.parquet')}) s
                ON s.source_system = x.source_system
               AND s.source_customer_id = x.source_customer_id
              JOIN read_parquet({_sql_path(output_dir / 'silver_customers.parquet')}) c
                ON EXISTS (
                  SELECT 1 FROM linked crm_x
                  WHERE crm_x.source_system = 'crm'
                    AND crm_x.source_customer_id = c.crm_id
                    AND crm_x.golden_customer_id = x.golden_customer_id
                )
              GROUP BY 1, 2
            )
            SELECT x.source_system, x.source_customer_id, x.match_method,
                   x.match_confidence, x.link_status,
                   e.dob_match, e.postal_match, e.phone_match, e.surname_match
            FROM linked x LEFT JOIN evidence e
              ON e.source_system = x.source_system
             AND e.source_customer_id = x.source_customer_id
            ORDER BY x.source_system, x.source_customer_id
        """, [golden_id]).fetchall()
    finally:
        con.close()

    explanations = []
    for system, source_id, method, confidence, status, dob, postal, phone, surname in rows:
        if system == "crm":
            evidence = ["CRM source record; duplicate grouping uses national-ID hash or explicit duplicate reference"]
        elif system == "collections":
            evidence = [
                "CRM customer reference" if method == "crm_reference"
                else "unanimous linked account fallback"
            ]
        else:
            evidence = [name for name, matched in (
                ("date of birth", dob), ("postcode", postal),
                ("phone", phone), ("surname", surname),
            ) if matched]
        explanations.append({
            "source_system": system,
            "source_customer_id": source_id,
            "match_method": method,
            "match_confidence": float(confidence),
            "link_status": status,
            "evidence": evidence,
        })
    return {
        "golden_customer_id": golden_id,
        "linked_source_count": len(explanations),
        "links": explanations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("golden_customer_id")
    parser.add_argument("--output-dir", type=Path, default=Path("local_artifacts/c360"))
    args = parser.parse_args()
    print(json.dumps(explain_customer(args.golden_customer_id, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
