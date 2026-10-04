# Run the Collections demo with Docker Compose

Docker Compose provides the same Python environment on Windows, Linux, and macOS. The image contains application code and pinned packages. It **does not** contain the dataset, generated C360/features, `.env`, or API keys.

## Prerequisites

1. Install Docker Desktop or Docker Engine with Compose. Start Docker before running the commands below. On Windows, open a new terminal after installation so `docker` is on `PATH`.
2. Download and extract the core synthetic release into `maple_data/maple_collections_release/` using the [dataset guide](DATASET_DOWNLOAD.md). The file `maple_data/maple_collections_release/data/customers.csv` must exist. The optional voice ZIP is not needed.
3. Run the commands from the repository root. Keep at least 6 GB available to Docker for the C360 build; the application itself uses smaller DuckDB memory limits. Do not run the C360 build, feature generation, and benchmark together.

## First run

Run these commands **in order**. The bootstrap command executes C360 and feature preparation **sequentially**, so the large jobs do not compete for memory:

```text
docker compose build
docker compose run --rm collections python -m app.bootstrap
docker compose run --rm collections python -m pytest tests -q
docker compose up -d collections
```

Open **http://localhost:8504**. Use the local demo accounts `manager / demo` or `agent / demo`, unless `COLLECTIONS_DEMO_PASSWORD` is set. To view status, run `docker compose ps`; to stop the app, run `docker compose down`.

If this checkout already has current `local_artifacts/` outputs, the build commands can be skipped: `docker compose build`, `docker compose run --rm collections python -m pytest tests -q`, then `docker compose up -d collections` are enough. Rebuild C360 and features after replacing the release.

## What is mounted

| Host path | Container path | Purpose |
| --- | --- | --- |
| `./maple_data` | `/workspace/maple_data` | Downloaded release, read-only |
| `./local_artifacts` | `/workspace/local_artifacts` | Generated C360, features, caches, and local audit |
| `./submission` | `/workspace/submission` | Submission outputs |

The optional, ignored `.env` file is read by Compose and passed to the container **at runtime**. It is excluded from the Docker build context. Set `INSIGHTS_LLM_PROVIDER` and the corresponding API key there only if you need questions that use an external SQL planner. Deterministic demo questions work without an API key. Do not print `docker compose config` or share container environment output when secrets are configured.

The default host port is **8504** to coexist with a local Streamlit server on 8501. Set `COLLECTIONS_PORT` to another unused host port if needed. The container always listens on 8501.

This is a local synthetic-data prototype. The demo login is not production authentication, and Compose does not add production authorization or customer-contact execution.
