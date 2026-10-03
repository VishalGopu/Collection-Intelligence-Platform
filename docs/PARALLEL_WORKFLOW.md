# Parallel build workflow

The C360 laptop now works on `feature/c360`; the Questions laptop can continue on `main` or use its own branch. Avoid conflicts through directory ownership and frequent synchronization. The shared contract is `contracts/golden_c360_v1.json`. If a field or path changes on the C360 branch, the Questions laptop should use its own raw views until the contract change reaches `main`.

## This laptop: C360

Own `src/c360/` and `tests/c360/`. Read the local dataset from `maple_data/maple_collections_release/`. Write generated Parquet and reports under `local_artifacts/c360/`. Publish the two Parquet files named in the contract. Do not edit `src/insights/`.

This checkout is already on `feature/c360`. Push it with `git push -u origin feature/c360`; merge it into `main` after its output contract and quality report are reviewed.

## Second laptop: Questions

```powershell
git clone git@github.com:VishalGopu/Collection-Intelligence-Platform.git
cd Collection-Intelligence-Platform
```

Follow `docs/DATASET_DOWNLOAD.md` on that laptop. Own `src/insights/` and `tests/insights/`. Start with `data/metric_definitions.csv`, `data/benchmark_questions.csv`, `labels/benchmark_dev_answers.csv`, and the policy documents. Use read-only raw views until C360 output is available. Join Collections cases to C360 through `identity_crosswalk.parquet` using `source_system = 'collections'` and `collections_cases.coll_customer_ref = source_customer_id`; CRM-keyed contacts, promises, and notes use `source_system = 'crm'`. Include only linked, approved identities. Do not edit `src/c360/`.

## Shared rules

- Keep code, tests, and module-specific dependencies inside the owning module's folder. Avoid changing root files or `contracts/` independently on both laptops.
- Use `golden_customer_id` as the shared customer key. Preserve source IDs as strings so leading zeros survive.
- Never commit `maple_data/`, `.venv/`, or `local_artifacts/`. Commit final benchmark answers and reports under `submission/` after integration.
- On `main`, run `git pull --ff-only origin main` before each work session. Before pushing, run `git pull --rebase origin main`, then `git push origin main`.
- On `feature/c360`, run `git fetch origin` regularly and merge `origin/main` when needed. Push with `git push origin feature/c360`. Never force-push `main`.
- If a shared contract or root-file change is necessary, agree on one laptop to make and push it; the other pulls before continuing.
- Keep generated C360 Parquet files local. After C360 code lands on `main`, the second laptop pulls `main` and runs that pipeline against its own dataset copy to create the same `local_artifacts/c360/` files. Do not move large data files through Git.
- After Layers 1 and 2 are integrated, add Layers 3 and 4 under `src/features/` and `src/decisioning/`, then run the end-to-end demo and benchmark.

The deadline in `build_phase.pdf` is 9:00 PM IST on 4 October 2026. The extra benchmark questions arrive at 7:00 PM IST that day.
