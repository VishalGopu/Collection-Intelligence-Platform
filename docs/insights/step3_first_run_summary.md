# Layer 2 uncached first run: 24 fresh-style + 10 blind questions

Run on 4 October 2026 with `--no-llm-cache`, unchanged prompt version `layer2-sql-v8`, and a 2 GB DuckDB limit. The full first-run answer, SQL or refusal evidence, time, retries, and rate-limit wait for each question is in [step3_first_run_34.csv](step3_first_run_34.csv).

- Non-error executions: 33/34. These questions have no published gold answers; this is not an accuracy score.
- Reference SQL matches: 9/10.
- Total wall time: 349.93 seconds, including 136.98 seconds setup.
- API calls: 38; cache hits: 0; retries: 10; rate limits: 18; rate-limit waits: 172.0 seconds.
- NQ-008 (open cases by assigned team) failed after three Groq HTTP 400 `json_validate_failed` responses; no SQL executed. Its reference comparison therefore failed. The prompt was not changed before this report. A fixed SQL route for this exact question was added after preserving the first-run result.
- The Windows relative-date tests pass and the source uses `resolved.day` rather than platform-specific `%-d` formatting.
