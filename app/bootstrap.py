"""Build the local demo data in a safe, sequential order.

Run from the repository root: python -m app.bootstrap
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


STEPS = (
    ("Build the golden C360", ("-m", "src.c360.build")),
    ("Prepare customer lookup", ("-m", "app.prepare_customer_data")),
    ("Create point-in-time promise features", ("-m", "src.features.training")),
    ("Create open-promise candidates", (
        "-m", "src.features.candidates", "--base",
        "local_artifacts/features/open_promise_features.parquet", "--output",
        "local_artifacts/features/open_promise_candidates.parquet")),
    ("Extract text rules", ("-m", "src.features.text_rules")),
    ("Prepare dated text features", ("-m", "src.features.text_data")),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show-steps", action="store_true",
                        help="Print the commands without building data")
    args = parser.parse_args()
    release = Path("maple_data/maple_collections_release/data/customers.csv")
    if not args.show_steps and not release.is_file():
        parser.error(f"Extract the synthetic release first; missing {release}")
    for label, arguments in STEPS:
        command = [sys.executable, *arguments]
        print(f"{label}: {' '.join(command)}", flush=True)
        if not args.show_steps:
            subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
