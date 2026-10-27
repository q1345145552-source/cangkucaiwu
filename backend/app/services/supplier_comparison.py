"""Legacy quote display only; no FX, price mutations or financial policies."""
from fastapi import HTTPException
import json


def ai_comparison_text(rows, mode):
    if mode not in ('product', 'logistics') or not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise HTTPException(400, '比价数据格式不正确')
    if any(not row.get('currency') or row.get('comparable') is False for row in rows):
        raise HTTPException(400, '报价币种或计价依据不完整，请人工核对后再分析')
    if len({row['currency'] for row in rows}) != 1:
        raise HTTPException(400, '不同币种不可混合比价，请先选择单一币种')
    allowed = ('supplier_name', 'product_name', 'spec', 'unit', 'unit_price', 'currency') if mode == 'product' else (
        'supplier_name', 'transport_method', 'cargo_type', 'origin_warehouse', 'price_per_cbm', 'min_cbm', 'min_amount', 'currency', 'estimated_days')
    return json.dumps([{key: row.get(key) for key in allowed} for row in rows], ensure_ascii=False)


def group_ranks(rows, fields, price_field):
    def group(row):
        return tuple(str(row.get(key) or '') for key in fields)

    rows.sort(key=lambda row: (group(row), row[price_field] is None, row[price_field] or 0, row.get('product_id', row.get('price_id', 0))))
    counters = {}
    for row in rows:
        key = group(row)
        if row[price_field] is None:
            row['rank_in_group'] = None
        else:
            counters[key] = counters.get(key, 0) + 1
            row['rank_in_group'] = counters[key]
        row['comparison_group'] = dict(zip(fields, key))
