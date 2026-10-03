# Maple Collections dataset: download and setup

The build phase uses the synthetic [Maple Bank Collections Hackathon dataset](https://huggingface.co/datasets/nuxsh/maple-collections-hackathon). The required `maple_collections_release.zip` contains 31 tables, call transcripts, policy documents, public NLP labels, schema files, and benchmark questions. `maple_collections_voice.zip` contains optional WAV recordings. The transcripts in the core release are sufficient for a text-based Layer 3 feature.

Run the commands below in PowerShell from the repository root. Allow about 10 GB of free disk space for the core archive plus extraction, or about 16 GB if you also download the voice pack. The dataset is ignored by Git through `/.gitignore`.

## Core release

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U huggingface_hub
.\.venv\Scripts\hf.exe download nuxsh/maple-collections-hackathon maple_collections_release.zip README.md --repo-type dataset --local-dir maple_data
.\.venv\Scripts\python.exe -m zipfile -e .\maple_data\maple_collections_release.zip .\maple_data
```

If the Hugging Face CLI stalls during the ZIP transfer, the repository also includes a resumable direct downloader. Run `python download_release.py` from the repository root, then run the extraction command above.

Check the result:

```powershell
Test-Path .\maple_data\maple_collections_release\README.md
Test-Path .\maple_data\maple_collections_release\data\customers.csv
Test-Path .\maple_data\maple_collections_release\data\benchmark_questions.csv
.\.venv\Scripts\python.exe -c "import zipfile; z=zipfile.ZipFile('maple_data/maple_collections_release.zip'); print(z.testzip() or 'ZIP CRC OK')"
```

Read `maple_data/maple_collections_release/README.md` before loading tables. It lists every table and source-system key. Preserve leading zeros in identifiers by loading keys as text. Empty CSV fields are null, but codes such as `NA` may be meaningful values. The provided `schema/load_duckdb.sql` creates views over the CSV and Parquet data. The benchmark files are in `data/benchmark_questions.csv` and `labels/`.

## Optional voice pack

Only download this if the project will process the WAV recordings. The core release already has note text and transcript text.

```powershell
.\.venv\Scripts\hf.exe download nuxsh/maple-collections-hackathon maple_collections_voice.zip --repo-type dataset --local-dir maple_data
.\.venv\Scripts\python.exe -m zipfile -e .\maple_data\maple_collections_voice.zip .\maple_data\voice_extracted
```

Follow the release README to copy the voice pack's `files/` folder into `maple_data/maple_collections_release/`. The voice pack is also covered by the dataset Git ignore rule.
