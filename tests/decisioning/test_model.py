import csv
from pathlib import Path

import duckdb
import pytest

from src.decisioning.model import PromiseModel, reason_sentence, DEFAULT_MODEL
from src.decisioning.train import compare_existing_scores
from src.features.training import FEATURE_COLUMNS


def test_committed_model_uses_allowlisted_columns_and_true_shap_reasons():
    if not DEFAULT_MODEL.is_file():
        pytest.skip('Model artifact has not been built')
    model = PromiseModel()
    values = {name: 1.0 for name in model.columns}
    scored = model.score(values)
    assert 0 < scored['probability'] < 1
    assert len(scored['shap_reasons']) == 3
    assert all(reason['feature'] in FEATURE_COLUMNS for reason in scored['shap_reasons'])
    sentence = reason_sentence(scored['shap_reasons'], 'call')
    assert all(reason['label'] in sentence for reason in scored['shap_reasons'])
    with pytest.raises(ValueError):
        model.score({**values, 'vulnerability_flag': 1})


def test_existing_score_comparison_rejects_future_and_protected_scores(tmp_path: Path):
    dataset = tmp_path / 'data'
    dataset.mkdir()
    with (dataset / 'model_scores.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['model_name','crm_customer_id','ptp_id',
            'score_ts','score','uses_protected_attributes'])
        writer.writeheader()
        writer.writerows([
            {'model_name':'ptp_break','crm_customer_id':'0001','ptp_id':'PTP-1',
             'score_ts':'2026-07-15 10:00:00','score':'0.4','uses_protected_attributes':'false'},
            {'model_name':'ptp_break','crm_customer_id':'0001','ptp_id':'PTP-1',
             'score_ts':'2026-07-20 10:00:00','score':'0.9','uses_protected_attributes':'true'},
            {'model_name':'ptp_break','crm_customer_id':'0001','ptp_id':'PTP-1',
             'score_ts':'2026-08-02 10:00:00','score':'0.2','uses_protected_attributes':'false'},
            {'model_name':'ptp_break','crm_customer_id':'0002','ptp_id':'PTP-2',
             'score_ts':'2026-07-15 10:00:00','score':'0.7','uses_protected_attributes':'false'},
        ])
    con = duckdb.connect()
    table = tmp_path / 'test.parquet'
    con.execute("""COPY (SELECT * FROM (VALUES
        ('PTP-1','0001',TIMESTAMP '2026-08-01 12:00:00',1),
        ('PTP-2','0002',TIMESTAMP '2026-08-01 12:00:00',0))
        AS t(ptp_id,crm_customer_id,promise_created_ts,label_kept)) TO ? (FORMAT PARQUET)""", [str(table)])
    scores = compare_existing_scores(con, table, tmp_path, {'PTP-1':(0.5,0.6),'PTP-2':(0.4,0.3)})
    direct = scores['ptp_break']['eligible_comparison']
    assert direct['rows'] == 2
    assert direct['roc_auc'] == 1.0  # 1-0.4 for PTP-1, 1-0.7 for PTP-2
    assert scores['ptp_break']['same_rows_lightgbm']['rows'] == 2
    con.close()
