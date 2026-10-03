# Layer 2 timing profile

The original 448-second run did not have per-stage instrumentation. The first instrumented cold-data-cache follow-up took 382.89 seconds: 86.90 seconds to build the DuckDB cache, 22.96 seconds in API requests, 0.61 seconds executing answer SQL, and the balance in repeated catalog construction and retry waits. The catalog is now built once per run.

The final prompt-v8, fresh-response-cache 24-question run took 181.66 seconds (27.64 setup, 22.57 API, 0.20 DuckDB execution, 131.25 other, mostly Retry-After waits). It made 24 API attempts, had 0 response-cache hits, and matched 10/10 independent reference SQL results.

| Question | Wall s | API s | DuckDB s | Other s | API calls | Cache hits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ-001 | 1.930 | 1.898 | 0.010 | 0.021 | 1 | 0 |
| NQ-002 | 1.152 | 1.130 | 0.012 | 0.010 | 1 | 0 |
| NQ-003 | 1.397 | 1.376 | 0.009 | 0.012 | 1 | 0 |
| NQ-004 | 1.199 | 1.184 | 0.004 | 0.011 | 2 | 0 |
| NQ-005 | 1.845 | 1.823 | 0.007 | 0.014 | 2 | 0 |
| NQ-006 | 37.059 | 2.034 | 0.006 | 35.019 | 3 | 0 |
| NQ-007 | 1.715 | 1.667 | 0.031 | 0.016 | 1 | 0 |
| NQ-008 | 33.560 | 2.482 | 0.067 | 31.011 | 3 | 0 |
| NQ-009 | 2.159 | 2.140 | 0.007 | 0.012 | 1 | 0 |
| NQ-010 | 39.193 | 2.169 | 0.010 | 37.014 | 3 | 0 |
| NQ-011 | 1.635 | 1.588 | 0.028 | 0.019 | 1 | 0 |
| NQ-012 | 1.597 | 1.583 | 0.003 | 0.011 | 1 | 0 |
| NQ-013 | 29.505 | 1.492 | 0.002 | 28.011 | 4 | 0 |
| NQ-014 | 0.007 | 0.000 | 0.000 | 0.007 | 0 | 0 |
| NQ-015 | 0.006 | 0.000 | 0.000 | 0.006 | 0 | 0 |
| NQ-016 | 0.007 | 0.000 | 0.000 | 0.007 | 0 | 0 |
| NQ-017 | 0.007 | 0.000 | 0.000 | 0.007 | 0 | 0 |
| NQ-018 | 0.006 | 0.000 | 0.000 | 0.006 | 0 | 0 |
| NQ-019 | 0.006 | 0.000 | 0.000 | 0.006 | 0 | 0 |
| NQ-020 | 0.006 | 0.000 | 0.000 | 0.006 | 0 | 0 |
| NQ-021 | 0.006 | 0.000 | 0.000 | 0.006 | 0 | 0 |
| NQ-022 | 0.006 | 0.000 | 0.000 | 0.006 | 0 | 0 |
| NQ-023 | 0.003 | 0.000 | 0.000 | 0.003 | 0 | 0 |
| NQ-024 | 0.007 | 0.000 | 0.000 | 0.007 | 0 | 0 |

The 60-question mixed run took 55.78 seconds (26.03 setup, 2.37 API, 25.70 DuckDB), with 1 live API call and 13 response-cache hits. It comprised 24 new questions, 35 released questions, and one additional new queue question. This verifies the mixed workload target, not throughput for 60 uncached LLM questions. Parallel dispatch is deliberately not enabled by default because Groq's per-model request/token limits can turn concurrency into longer Retry-After waits.
