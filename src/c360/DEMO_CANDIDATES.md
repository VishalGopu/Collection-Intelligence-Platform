# Demo customer candidates

Generated from the 28 September 2026 release with `python src/c360/demo_candidates.py`. The query requires `link_status = 'linked'` on the Collections crosswalk, more than one CRM record in the golden customer, at least one broken promise, and a linked case with notes or transcripts. Counts are for linked cases only. No personal or fairness-test fields are included.

| Golden customer ID | Why this is useful for the demo |
| --- | --- |
| `G-39c6b287f70371cd9fc6` | Two CRM records resolved to one customer; one linked open case, three broken promises, 12 notes, three transcripts, and a hardship flag. Good for explaining identity and showing several call records. |
| `G-ce8c778700c9b95b55d8` | Two CRM records; one linked open case, two broken promises, 15 notes, three transcripts, and a hardship flag. Good for comparing an answer against multiple transcripts. |
| `G-f4b22f89068d857ebe87` | Two CRM records; one linked open case, four broken promises, 18 notes, two transcripts, and a hardship flag. Strong candidate for the promise-history and specialist-review path. |
| `G-39214e6dde2a06706f89` | Two CRM records; one linked open case, two broken promises, 21 notes, two transcripts, and a hardship flag. Richest note history among these five. |
| `G-42ba77893259d13e6b27` | Two CRM records; one linked open case, two broken promises, 14 notes, two transcripts, and a hardship flag. A compact alternative with both text sources. |

These are selection candidates, not approved customer actions. The app should load current case facts and apply its policy gate before showing a recommendation.
