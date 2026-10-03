# Full linked test-period fairness measurement

All 52,283 linked, quality-passed, resolved promises created from 1 July to 28 September 2026. The model is scored first; only this restricted script then joins gender_code and citizenship_status for measurement.

95% intervals: customer-clustered normal standard-error intervals for mean predicted risk, observed broken rate and channel shares. Intervals describe sampling uncertainty within this synthetic cohort, not causal uncertainty or representativeness.

| Field | Group | N | Mean predicted break risk (95% CI) | Observed broken rate (95% CI) | Last pre-promise outbound channel (share, 95% CI) |
| --- | --- | ---: | ---: | ---: | --- |
| gender_code | F | 25,109 | 0.540 [0.537, 0.543] | 0.620 [0.614, 0.626] | call: 39.2% [38.6%, 39.8%]; email: 14.9% [14.5%, 15.4%]; letter: 11.1% [10.7%, 11.5%]; none: 17.5% [17.0%, 18.0%]; push: 3.0% [2.7%, 3.2%]; sms: 14.3% [13.9%, 14.8%] |
| gender_code | M | 25,711 | 0.541 [0.538, 0.544] | 0.628 [0.622, 0.634] | call: 39.0% [38.3%, 39.6%]; email: 15.5% [15.0%, 15.9%]; letter: 11.1% [10.7%, 11.5%]; none: 17.3% [16.8%, 17.7%]; push: 2.9% [2.7%, 3.1%]; sms: 14.3% [13.9%, 14.8%] |
| gender_code | U | 483 | 0.507 [0.488, 0.526] | 0.607 [0.562, 0.651] | call: 34.6% [30.1%, 39.1%]; email: 14.5% [11.1%, 17.9%]; letter: 13.9% [10.8%, 17.0%]; none: 19.5% [15.8%, 23.2%]; push: 2.9% [1.4%, 4.4%]; sms: 14.7% [11.4%, 18.0%] |
| gender_code | X | 485 | 0.543 [0.523, 0.564] | 0.647 [0.603, 0.692] | call: 35.1% [30.5%, 39.6%]; email: 18.1% [14.4%, 21.9%]; letter: 11.5% [8.6%, 14.5%]; none: 16.9% [13.5%, 20.3%]; push: 4.1% [2.4%, 5.9%]; sms: 14.2% [11.0%, 17.5%] |
| gender_code | unknown | 495 | 0.531 [0.511, 0.551] | 0.632 [0.590, 0.675] | call: 40.6% [35.9%, 45.3%]; email: 16.8% [13.3%, 20.3%]; letter: 8.3% [5.8%, 10.7%]; none: 17.4% [13.9%, 20.8%]; push: 2.8% [1.4%, 4.3%]; sms: 14.1% [11.1%, 17.2%] |
| citizenship_status | citizen | 39,921 | 0.544 [0.542, 0.546] | 0.630 [0.625, 0.635] | call: 39.3% [38.8%, 39.8%]; email: 15.2% [14.8%, 15.6%]; letter: 11.1% [10.8%, 11.4%]; none: 17.2% [16.8%, 17.6%]; push: 3.0% [2.8%, 3.1%]; sms: 14.2% [13.9%, 14.6%] |
| citizenship_status | permanent_resident | 7,762 | 0.530 [0.525, 0.535] | 0.610 [0.598, 0.621] | call: 38.5% [37.4%, 39.7%]; email: 14.8% [14.0%, 15.7%]; letter: 11.5% [10.8%, 12.2%]; none: 17.7% [16.8%, 18.6%]; push: 3.0% [2.6%, 3.3%]; sms: 14.5% [13.7%, 15.3%] |
| citizenship_status | study_permit | 1,734 | 0.523 [0.512, 0.534] | 0.588 [0.564, 0.613] | call: 36.0% [33.7%, 38.4%]; email: 15.4% [13.7%, 17.1%]; letter: 10.8% [9.3%, 12.3%]; none: 19.6% [17.6%, 21.5%]; push: 2.9% [2.1%, 3.7%]; sms: 15.3% [13.5%, 17.0%] |
| citizenship_status | unknown | 542 | 0.535 [0.515, 0.555] | 0.603 [0.563, 0.644] | call: 36.2% [31.9%, 40.4%]; email: 17.7% [14.3%, 21.1%]; letter: 10.1% [7.4%, 12.9%]; none: 16.8% [13.6%, 20.0%]; push: 3.5% [2.0%, 5.1%]; sms: 15.7% [12.5%, 18.9%] |
| citizenship_status | work_permit | 2,324 | 0.524 [0.515, 0.534] | 0.616 [0.595, 0.636] | call: 38.9% [36.7%, 41.0%]; email: 16.0% [14.5%, 17.5%]; letter: 10.3% [9.1%, 11.6%]; none: 17.9% [16.3%, 19.5%]; push: 2.6% [2.0%, 3.3%]; sms: 14.3% [12.8%, 15.7%] |

Break-rate drift: pre-July training 35.7% broken versus 62.5% in this linked test cohort. This temporal shift limits calibration and group comparisons.

The channel mix is the **observed last outbound channel in the prior 30 days**, not a recommendation from this model. Agents selected those channels. No uplift or differential-treatment cause is inferred.

**Plain summary**
1. Measured predicted risk, actual broken rate and historical channel mix for 52,283 linked test-period promises; protected fields are measurement-only.
2. Women/men have similar mean predicted risk (0.540/0.541); citizens show 0.544 versus 0.530 for permanent residents, alongside observed broken rates 0.630 versus 0.610. These are descriptive gaps.
3. Broken-rate drift (35.7% to 62.5%) and observational channel selection prevent causal fairness or uplift claims.
