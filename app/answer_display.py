"""Turn Ask's CSV-shaped results into readable display data."""

from __future__ import annotations

import csv
import io
import re


STRUCTURED_MODES = {"structured", "scoped_sql", "llm_sql", "empty"}


def display_answer(answer: str, mode: str) -> dict:
    if mode not in STRUCTURED_MODES:
        return {"kind": "text", "text": answer}
    if answer.strip().rstrip(".") == "No rows matched":
        return {"kind": "empty"}
    rows = list(csv.reader(io.StringIO(answer)))
    if len(rows) < 2:
        return {"kind": "empty"} if rows else {"kind": "text", "text": answer}
    headers = rows[0]
    if headers and headers[0] == "total_open_cases" and all(row[0] == rows[1][0] for row in rows[1:]):
        total = int(rows[1][0])
        items = [dict(zip(headers[1:], row[1:])) for row in rows[1:]
                 if any(value for value in row[1:])]
        return {"kind": "table_with_total", "label": "Open cases",
                "value": f"{total:,}", "rows": items}
    if len(headers) == 1 and len(rows) == 2 and len(rows[1]) == 1:
        label = headers[0].replace("_", " ").replace("60plus", "60+").title().replace("Dpd", "DPD")
        value = rows[1][0]
        if re.fullmatch(r"-?\d+", value):
            value = f"{int(value):,}"
        elif re.fullmatch(r"-?\d+\.\d+", value):
            whole, fraction = value.split(".", 1)
            value = f"{int(whole):,}.{fraction}"
        return {"kind": "metric", "label": label, "value": value}
    return {"kind": "table", "rows": [dict(zip(headers, row)) for row in rows[1:]]}
