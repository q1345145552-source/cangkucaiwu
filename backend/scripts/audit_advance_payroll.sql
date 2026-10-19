-- PostgreSQL 16+，只读审计，不修改或重算历史工资单。
-- 同时统计已作废历史和当前有效工资；金额按预支币种分列。
BEGIN READ ONLY;
WITH payroll AS (
    SELECT id, warehouse_id, employee_id, created_at,
           COALESCE(voided, false) AS voided,
           COALESCE(advance_deduction, 0)::numeric AS deduction,
           detail IS JSON OBJECT AS valid_detail,
           CASE WHEN detail IS JSON OBJECT THEN detail::jsonb ELSE '{}'::jsonb END AS data
    FROM payroll_records
), entries AS (
    SELECT p.*, line
    FROM payroll p
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(data->'advance_deductions') = 'array'
             THEN data->'advance_deductions' ELSE '[]'::jsonb END
    ) line
), parsed AS (
    SELECT *,
           CASE WHEN line->>'advance_id' ~ '^[0-9]{1,10}$' THEN (line->>'advance_id')::bigint END AS advance_id,
           CASE WHEN line->>'amount' ~ '^[+]?[0-9]+([.][0-9]+)?$'
                THEN (line->>'amount')::numeric END AS amount
    FROM entries
), linked AS (
    SELECT p.*, a.id AS matched_id, a.approval_status, a.reviewed_at,
           CASE WHEN a.id IS NOT NULL THEN COALESCE(a.currency, 'THB') ELSE '<unknown>' END AS currency
    FROM parsed p
    LEFT JOIN employee_advances a ON a.id = p.advance_id
        AND a.employee_id = p.employee_id AND a.warehouse_id = p.warehouse_id
), flagged AS (
    SELECT *, CASE
        WHEN approval_status IN ('pending', 'rejected') THEN 'currently_unapproved'
        WHEN approval_status = 'approved' AND reviewed_at > created_at THEN 'approved_after_payroll_creation'
    END AS issue
    FROM linked WHERE amount > 0 AND matched_id IS NOT NULL
), issues AS (
    SELECT issue, warehouse_id, currency,
           count(DISTINCT id) AS payroll_count,
           count(DISTINCT id) FILTER (WHERE NOT voided) AS active_payroll_count,
           count(*) AS deduction_line_count,
           round(sum(amount), 2) AS amount,
           round(COALESCE(sum(amount) FILTER (WHERE NOT voided), 0), 2) AS active_amount
    FROM flagged WHERE issue IS NOT NULL
    GROUP BY issue, warehouse_id, currency
), unresolved AS (
    SELECT *, CASE
        WHEN matched_id IS NULL THEN 'missing_or_foreign_advance'
        WHEN approval_status = 'approved' AND reviewed_at IS NULL THEN 'approval_time_missing'
        WHEN approval_status IS NULL OR approval_status NOT IN ('approved','pending','rejected') THEN 'unknown_approval_status'
    END AS reason
    FROM linked WHERE amount > 0
), unresolved_totals AS (
    SELECT reason, warehouse_id, currency, count(DISTINCT id) AS payroll_count,
           count(DISTINCT id) FILTER (WHERE NOT voided) AS active_payroll_count,
           count(*) AS deduction_line_count, round(sum(amount), 2) AS amount,
           round(COALESCE(sum(amount) FILTER (WHERE NOT voided), 0), 2) AS active_amount
    FROM unresolved WHERE reason IS NOT NULL GROUP BY reason, warehouse_id, currency
), line_totals AS (
    SELECT id, sum(amount) FILTER (WHERE amount > 0) AS amount
    FROM parsed GROUP BY id
)
SELECT jsonb_build_object(
    'checked_at', CURRENT_TIMESTAMP,
    'transaction_read_only', current_setting('transaction_read_only'),
    'payroll_count', (SELECT count(*) FROM payroll),
    'payroll_with_advance_deduction', (SELECT count(*) FROM payroll WHERE deduction > 0),
    'advance_count', (SELECT count(*) FROM employee_advances),
    'advance_approval_statuses', (SELECT COALESCE(jsonb_object_agg(status, n), '{}'::jsonb) FROM (
        SELECT COALESCE(approval_status, '<null>') status, count(*) n FROM employee_advances GROUP BY approval_status
    ) statuses),
    'linked_deduction_line_count', (SELECT count(*) FROM linked WHERE amount > 0 AND matched_id IS NOT NULL),
    'currently_unapproved_payroll_count', (SELECT count(DISTINCT id) FROM flagged WHERE issue = 'currently_unapproved'),
    'approved_after_creation_payroll_count', (SELECT count(DISTINCT id) FROM flagged WHERE issue = 'approved_after_payroll_creation'),
    'issues_by_warehouse_currency', (SELECT COALESCE(jsonb_agg(to_jsonb(i) ORDER BY issue, warehouse_id, currency), '[]'::jsonb) FROM issues i),
    'unresolved_by_warehouse_currency', (SELECT COALESCE(jsonb_agg(to_jsonb(u) ORDER BY reason, warehouse_id, currency), '[]'::jsonb) FROM unresolved_totals u),
    'missing_or_foreign_advance_details', (SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'payroll_id', id, 'advance_id', advance_id, 'warehouse_id', warehouse_id,
        'employee_id', employee_id, 'amount', amount, 'voided', voided
    ) ORDER BY id, advance_id), '[]'::jsonb) FROM linked WHERE amount > 0 AND matched_id IS NULL),
    'coverage', jsonb_build_object(
        'missing_or_foreign_advance_lines', (SELECT count(*) FROM linked WHERE amount > 0 AND matched_id IS NULL),
        'invalid_deduction_lines', (SELECT count(*) FROM parsed WHERE advance_id IS NULL OR amount IS NULL OR amount <= 0),
        'deduction_without_valid_detail', (SELECT count(*) FROM payroll WHERE deduction > 0 AND valid_detail IS NOT TRUE),
        'deduction_detail_amount_mismatch', (SELECT count(*) FROM payroll p LEFT JOIN line_totals t USING(id)
            WHERE abs(p.deduction - COALESCE(t.amount, 0)) > 0.009),
        'approved_without_review_time_lines', (SELECT count(*) FROM linked
            WHERE amount > 0 AND matched_id IS NOT NULL AND approval_status = 'approved' AND reviewed_at IS NULL),
        'unknown_approval_status_lines', (SELECT count(*) FROM linked
            WHERE amount > 0 AND matched_id IS NOT NULL AND (approval_status IS NULL OR approval_status NOT IN ('approved','pending','rejected')))
    ),
    'notes', jsonb_build_array(
        '当前待审批/已驳回仍被工资明细引用，或审批时间晚于工资创建时间，均列为待核对关联，不自动改账。',
        '包括已作废历史，active 字段单列当前有效工资，历史作废和重算不能当成多次实际扣款相加。',
        '审批时间缺失、预支已删除或明细不完整时，不能据此证明历史从未误扣；本审计不猜测缺失数据。'
    )
) AS advance_payroll_audit;
ROLLBACK;
