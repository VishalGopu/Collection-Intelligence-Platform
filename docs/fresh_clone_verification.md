# Fresh-clone verification (4 October 2026)

Environment: Windows, Python 3.14.3. Cloned the GitHub repository into a new
`fresh_clone_check` folder, created a new `.venv`, and installed the exact versions
in the single root `requirements.txt` with `python -m pip install -r requirements.txt`.
The clone used junctions to the already downloaded `maple_data` and generated
`local_artifacts` directories; those data files are not tracked by Git. A new
machine must download the dataset and build local artifacts as described in the
root README before data-dependent workflows can run.

`python -m pytest tests -q`: **183 passed**, 5 SHAP LightGBM representation
warnings, no failures (72.88 seconds). Started the app with
`python -m streamlit run app/main.py --server.headless=true --server.port=8502`.
`GET /_stcore/health` returned HTTP 200 and `ok`. Stopped that verification
process afterward.

The requirements file includes exact versions for SHAP 0.52.0, NumPy 2.5.3,
SciPy 1.18.1, Numba 0.68.0, llvmlite 0.50.0, scikit-learn 1.9.1, and slicer
0.0.8, plus the rest of the resolved environment.
