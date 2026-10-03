# Parallel build workflow

Both laptops start from `main`. Keep implementation on separate branches and directories. The shared contract is `contracts/golden_c360_v1.json`; treat it as frozen for the first integration. If a field or path must change, coordinate that change before either branch relies on it.

## This laptop: C360

```powershell
git switch -c feature/c360
```

Own `src/c360/` and `tests/c360/`. Read the local dataset from `maple_data/maple_collections_release/`. Write generated Parquet and reports under `local_artifacts/c360/`. Publish the two Parquet files named in the contract. Do not edit `src/insights/`.

## Second laptop: Questions

```powershell
git clone git@github.com:VishalGopu/Collection-Intelligence-Platform.git
cd Collection-Intelligence-Platform
git switch -c feature/insights
```

Follow `docs/DATASET_DOWNLOAD.md` on that laptop. Own `src/insights/` and `tests/insights/`. Start with `data/metric_definitions.csv`, `data/benchmark_questions.csv`, `labels/benchmark_dev_answers.csv`, and the policy documents. Use read-only raw views until C360 output is available. Join Collections records to C360 through `identity_crosswalk.parquet` using `source_system = 'crm'` and `collections_cases.coll_customer_ref = source_customer_id`. Include only linked, approved identities. Do not edit `src/c360/`.

## Shared rules

- Keep code, tests, and module-specific dependencies inside the owning module's folder. Avoid changing root files or `contracts/` independently on both branches.
- Use `golden_customer_id` as the shared customer key. Preserve source IDs as strings so leading zeros survive.
- Never commit `maple_data/`, `.venv/`, or `local_artifacts/`. Commit final benchmark answers and reports under `submission/` after integration.
- Push each branch with `git push -u origin <branch>` and merge through separate pull requests into `main`. Do not force-push `main`.
- If a shared contract change is necessary, land it on `main` first; then merge `origin/main` into each feature branch.
- Keep generated C360 Parquet files local. After C360 code lands on `main`, the second laptop pulls `main` and runs that pipeline against its own dataset copy to create the same `local_artifacts/c360/` files. Do not move large data files through Git.
- After both branches land, add Layers 3 and 4 under `src/features/` and `src/decisioning/`, then run the end-to-end demo and benchmark.

The deadline in `build_phase.pdf` is 9:00 PM IST on 4 October 2026. The extra benchmark questions arrive at 7:00 PM IST that day.
