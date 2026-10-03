from datetime import datetime

from src.features.text import features_at


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
