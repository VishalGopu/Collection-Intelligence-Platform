# Layer 2: Insight and NLP

Own certified metric queries, policy/document retrieval, out-of-scope refusal, cited answer cards, and automated benchmark answer generation. Keep implementation and module dependencies in this directory, and tests in `tests/insights/`.

Develop first against the release's read-only DuckDB views and benchmark files. When C360 is ready, consume only the paths and columns in `contracts/golden_c360_v1.json`. Every answer must show the executed SQL or source document/record IDs. Do not edit C360 pipeline code.
