# LightGBM Brier reconciliation

| Run | Fitting period | Calibration period | Test Brier |
| --- | --- | --- | ---: |
| Feature round / v2 LightGBM | Promises created and resolved before 1 July 2026 (137,149 rows) | None | 0.239136 |
| v3 raw LightGBM | Promises created and resolved before 1 May 2026 (121,784 rows) | None | 0.246476 |
| v3 isotonic LightGBM | Same 121,784 rows | 1 May–30 June, resolved before 1 July (13,465 distinct rows) | 0.224500 |

The earlier 0.2391 and current 0.2465 are **different fitted models**. The
current raw model reserves May–June cases to fit an isotonic calibrator, so it
trains on fewer and older promises. Both are measured on the same July-onward
test period (54,657 rows). The calibrator sees the raw model's predictions and
outcomes for its separate pre-July validation period only. No July-onward
outcome is used to fit either model or calibrator.

For context, the test broken-promise rate is 0.623873. A constant kept
probability equal to the observed test kept rate has Brier 0.234656 (oracle
reference, unavailable in deployment). The pre-July training kept rate as a
constant gives Brier 0.305885. Isotonic v3 improves on these references, but
the margin over the test-rate oracle is small and reliability remains imperfect
after a large label-rate shift. ROC AUC for the calibrated model is 0.676704;
isotonic ties can reduce ranking metrics relative to the raw v3 ROC AUC 0.678098.

Sources: `feature_round.json` (`selected_candidate`),
`promise_model_metrics.json` (`calibration_method`, `lightgbm_uncalibrated`,
`lightgbm`, `constant_prediction_brier`).
