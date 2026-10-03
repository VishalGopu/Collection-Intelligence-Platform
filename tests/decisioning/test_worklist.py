"""Open promise worklist smoke and point-in-time checks on the release."""

from pathlib import Path

import pytest

from src.decisioning import RecommendationEngine


@pytest.mark.skipif(not Path('local_artifacts/features/open_promise_features.parquet').is_file(),
                    reason='Build open promise features first')
def test_open_worklist_is_sorted_and_has_actual_shap_reasons():
    engine = RecommendationEngine()
    try:
        rows = engine.worklist(3)
        assert len(rows) == 3
        assert all(row['customer_id'].startswith('G-') for row in rows)
        assert all(len(row['shap_reasons']) == 3 for row in rows)
        assert all(row['top_reason'] == row['shap_reasons'][0]['label'] for row in rows)
        assert [row['probability_break'] for row in rows] == sorted(
            [row['probability_break'] for row in rows], reverse=True)
    finally:
        engine.close()
