from pathlib import Path

import pytest

from src.decisioning.restricted.fairness_test_period import run


@pytest.mark.skipif(not Path('local_artifacts/features/promise_training.parquet').is_file(),
                    reason='Full release required')
def test_full_linked_fairness_cohort_and_drift(tmp_path):
    result = run(tmp_path / 'fairness.md')
    assert result['rows'] > 50000
    assert result['test_break_rate'] > result['train_break_rate']
    groups = result['groups']
    assert sum(row['n'] for (field, _), row in groups.items()
               if field == 'gender_code') == result['rows']
    report = (tmp_path / 'fairness.md').read_text()
    assert 'customer-clustered' in report
    assert 'measurement-only' in report
