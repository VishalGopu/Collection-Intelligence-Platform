"""Certified, read-only SQL used by the Layer 2 benchmark runner."""

SQL_BY_QUESTION = {
    "BQ-003": """SELECT least(prior_broken_ptp_count, 3) AS prior_broken,
round(100.0 * avg(CASE WHEN ptp_status='broken' THEN 1 ELSE 0 END), 1) AS broken_rate_pct,
count(*) AS promises
FROM promises_to_pay
WHERE ptp_status IN ('kept','partially_kept','broken')
GROUP BY 1 ORDER BY 1""",
    "BQ-004": """SELECT queue, round(avg(current_dpd), 1) AS avg_dpd, count(*) AS open_cases
FROM collections_cases WHERE outcome IS NULL GROUP BY 1 ORDER BY 1""",
    "BQ-006": """SELECT CASE WHEN contact_ts_local >= TIMESTAMP '2026-09-15' THEN '15-22 Sep' ELSE '7-14 Sep' END AS period,
count(*) AS disputes
FROM contact_history
WHERE dispute_raised_flag AND contact_ts_local >= TIMESTAMP '2026-09-07'
AND contact_ts_local < TIMESTAMP '2026-09-23'
GROUP BY 1 ORDER BY 1""",
    "BQ-007": """SELECT coalesce(a.site, 'self_serve') AS site,
round(100.0 * avg(CASE WHEN p.ptp_status='broken' THEN 1 ELSE 0 END), 1) AS broken_rate_pct,
count(*) AS promises
FROM promises_to_pay p LEFT JOIN agents a ON a.agent_id = p.agent_id
WHERE p.ptp_due_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-28'
AND p.ptp_status IN ('kept','partially_kept','broken')
GROUP BY 1 ORDER BY 1""",
    "BQ-008": """SELECT round(100.0 * avg(CASE WHEN cure_flag AND days_to_cure <= 30 THEN 1 ELSE 0 END), 1) AS cure_rate_pct,
count(*) AS cases
FROM collections_cases
WHERE case_open_date >= DATE '2026-07-01' AND case_open_date < DATE '2026-08-01'
AND NOT insolvency_hold_flag AND NOT deceased_hold_flag""",
    "BQ-010": """SELECT c.province_code,
round(100.0 * avg(CASE WHEN NOT h.within_permitted_hours_flag THEN 1 ELSE 0 END), 2) AS out_of_hours_pct,
count(*) AS calls
FROM contact_history h JOIN collections_cases c ON c.case_id = h.case_id
WHERE coalesce(channel_v2, channel)='call' AND h.direction='outbound'
AND h.contact_ts_local >= TIMESTAMP '2026-09-01'
GROUP BY 1 ORDER BY 1""",
    "BQ-011": """SELECT contact_hour_local,
round(100.0 * avg(CASE WHEN rpc_flag THEN 1 ELSE 0 END), 1) AS rpc_rate_pct,
count(*) AS attempts
FROM contact_history
WHERE coalesce(channel_v2, channel)='call' AND direction='outbound'
AND contact_ts_local >= TIMESTAMP '2026-09-01' AND contact_ts_local < TIMESTAMP '2026-09-28'
GROUP BY 1 ORDER BY 1""",
    "BQ-012": """SELECT product_code,
round(100.0 * avg(CASE WHEN dpd >= 1 THEN 1 ELSE 0 END), 2) AS delinquency_rate_pct,
count(*) AS accounts
FROM card_accounts
WHERE snapshot_date = DATE '2026-09-28' AND account_status IN ('active','blocked') AND dpd IS NOT NULL
GROUP BY 1 ORDER BY 1""",
    "BQ-013": """SELECT round(sum(amount_paid_against), 2) AS amount_paid_cad
FROM promises_to_pay
WHERE paid_date >= DATE '2026-09-01' AND paid_date < DATE '2026-10-01'""",
    "BQ-014": """SELECT a.vulnerable_customer_certified AS certified,
round(100.0 * avg(CASE WHEN c.cure_flag AND c.days_to_cure <= 30 THEN 1 ELSE 0 END), 1) AS cure_rate_30d_pct,
count(*) AS hardship_cases
FROM collections_cases c JOIN agents a ON a.agent_id = c.assigned_agent_id
WHERE c.assignment_method = 'random' AND c.hardship_flag
GROUP BY 1 ORDER BY 1""",
    "BQ-015": """SELECT product, count(*) AS accounts, round(sum(chargeoff_amount), 2) AS chargeoff_cad
FROM (
  SELECT 'card:' || product_code AS product, chargeoff_amount FROM card_accounts
  WHERE chargeoff_date > DATE '2025-09-28' AND chargeoff_date <= DATE '2026-09-28'
  UNION ALL
  SELECT 'loan:' || product_type AS product, chargeoff_amount FROM loan_accounts
  WHERE chargeoff_date > DATE '2025-09-28' AND chargeoff_date <= DATE '2026-09-28'
) x GROUP BY 1 ORDER BY 1""",
    "BQ-017": """WITH s AS (
SELECT account_id, product_type,
coalesce(try_strptime(month_end_date, '%Y-%m-%d'), try_strptime(month_end_date, '%d/%m/%Y'),
try_strptime(month_end_date, '%Y%m%d'))::DATE AS me, dpd
FROM account_monthly_snapshot WHERE dpd IS NOT NULL)
SELECT a.product_type, round(100.0 * avg(CASE WHEN b.dpd > 30 THEN 1 ELSE 0 END), 1) AS roll_rate_pct,
count(*) AS accounts
FROM s a JOIN s b ON a.account_id = b.account_id AND b.me = DATE '2026-06-30'
WHERE a.me = DATE '2026-03-31' AND a.dpd BETWEEN 1 AND 30
GROUP BY 1 ORDER BY 1""",
    "BQ-025": """SELECT c.current_bucket,
round(count(h.contact_id)::DOUBLE / count(DISTINCT c.case_id), 2) AS attempts_per_case,
count(DISTINCT c.case_id) AS open_cases
FROM collections_cases c LEFT JOIN contact_history h ON h.case_id = c.case_id
AND h.direction = 'outbound' AND coalesce(h.channel_v2, h.channel) <> 'system'
WHERE c.outcome IS NULL GROUP BY 1 ORDER BY 1""",
    "BQ-027": """SELECT coalesce(channel_v2, channel) AS channel,
round(sum(contact_cost_cad) / count(contact_id), 2) AS cost_per_contact_cad,
count(*) AS contacts
FROM contact_history
WHERE contact_ts_local >= TIMESTAMP '2026-09-01' AND contact_ts_local < TIMESTAMP '2026-10-01'
AND coalesce(channel_v2, channel) <> 'system'
GROUP BY 1 ORDER BY 1""",
    "BQ-028": """SELECT c.test_cell,
round(100.0 * avg(CASE WHEN p.ptp_status='kept' THEN 1 ELSE 0 END), 1) AS kept_pct,
count(*) AS promises
FROM promises_to_pay p JOIN collections_cases c ON c.case_id = p.case_id
WHERE c.assignment_method = 'random' AND c.test_cell IN ('champion','challenger_A','challenger_B')
AND p.ptp_status IN ('kept','partially_kept','broken')
GROUP BY 1 ORDER BY 1""",
    "BQ-032": """SELECT primary_product,
round(100.0 * avg(CASE WHEN hardship_flag THEN 1 ELSE 0 END), 1) AS hardship_rate_pct,
count(*) AS cases
FROM collections_cases WHERE case_open_date >= DATE '2026-01-01'
GROUP BY 1 ORDER BY 1""",
    "BQ-034": """SELECT round(100.0 * sum(CASE WHEN ptp_status='kept' THEN 1 ELSE 0 END)
/ sum(CASE WHEN ptp_status IN ('kept','partially_kept','broken') THEN 1 ELSE 0 END), 1) AS promise_kept_rate_pct
FROM promises_to_pay WHERE ptp_due_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'""",
    "BQ-035": """SELECT current_bucket, count(*) AS open_cases
FROM collections_cases WHERE outcome IS NULL GROUP BY 1 ORDER BY 1""",
}
