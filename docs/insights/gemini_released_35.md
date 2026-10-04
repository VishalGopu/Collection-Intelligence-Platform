# Released benchmark with Gemini selected

Run on 4 October 2026 using the official `python -m src.insights.submission`
command, `maple_data/maple_collections_release/data/benchmark_questions.csv`,
and `INSIGHTS_LLM_PROVIDER=gemini`. The generated, unedited four-column output
is [gemini_released_35.csv](gemini_released_35.csv).

| Check | Result |
| --- | ---: |
| Released questions / output rows / unique IDs | 35 / 35 / 35 |
| Missing question IDs | 0 |
| Expected refusal IDs | BQ-018, BQ-023, BQ-024, BQ-029, BQ-031 |
| Non-refused rows without SQL or sources | 0 |
| Changed answer, evidence, or refusal from prior 35-row output | 0 |
| Development-answer comparison | 21 / 21 passed |

The released questions followed certified SQL, document, transcript, or refusal
routes, so this run verifies the full submission path with Gemini configured but
does **not** measure Gemini's accuracy or speed on unseen questions. A separate
uncached Gemini planning request returned SQL in 2.6 seconds with no retries;
an end-to-end ad hoc Ask request took 29.9 seconds, largely local data work.
