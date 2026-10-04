from datetime import datetime

from src.features.text import extract_rules, features_at
from src.features.text_data import evaluate_public


def test_training_and_live_text_definition_has_strict_cutoff_parity():
    events = [
        {'event_id': 'note:old', 'event_ts': datetime(2026, 6, 1)},
        {'event_id': 'transcript:later', 'event_ts': datetime(2026, 7, 1)},
    ]
    annotations = {
        'note:old': {'hardship_signal': 'possible', 'stated_delay_reason': 'payroll_timing'},
        'transcript:later': {'hardship_signal': 'clear', 'stated_delay_reason': 'reduced_income'},
    }
    cutoff = datetime(2026, 7, 1)
    training = features_at(events, cutoff, annotations)
    live = features_at(events, cutoff, annotations)
    assert training == live
    assert training['text_source_id'] == 'note:old'
    assert training['hardship_signal'] == 'possible'
    assert features_at(events, datetime(2026, 6, 1), annotations)['hardship_signal'] is None


def test_rule_extraction_and_training_live_cutoff_parity():
    annotations = {
        'note:old': extract_rules('My shifts at work were cut. I cannot pay the whole amount.'),
        'transcript:new': extract_rules('There was a problem with my bank transfer.'),
    }
    events = [
        {'event_id': 'note:old', 'event_ts': datetime(2026, 6, 1)},
        {'event_id': 'transcript:new', 'event_ts': datetime(2026, 7, 1)},
    ]
    cutoff = datetime(2026, 7, 1)
    training = features_at(events, cutoff, annotations)
    live = features_at(events, cutoff, annotations)
    assert training == live
    assert training['hardship_signal'] == 'clear'
    assert training['stated_delay_reason'] == 'reduced_income'
    assert training['text_source_id'] == 'note:old'
    assert features_at(events, datetime(2026, 6, 1), annotations)['text_source_id'] is None


def test_public_text_metrics_measure_both_signals_without_gold_leakage():
    labels = [{'id': 'note:1', 'source': 'note', 'hardship_signal': 'clear',
               'stated_delay_reason': 'reduced_income'},
              {'id': 'note:2', 'source': 'note', 'hardship_signal': 'none',
               'stated_delay_reason': None}]
    predictions = {'note:1': {'hardship_signal': 'possible',
                               'stated_delay_reason': 'payroll_timing'},
                   'note:2': {'hardship_signal': 'none',
                               'stated_delay_reason': None}}
    report = evaluate_public(labels, predictions)['note']
    assert report['hardship_clear_or_possible']['precision'] == 1
    assert report['hardship_clear_or_possible']['recall'] == 1
    assert report['stated_delay_reason_present']['precision'] == 1
    assert report['delay_reason_by_class']['reduced_income']['recall'] == 0
    assert report['delay_reason_exact_accuracy'] == 0.5
