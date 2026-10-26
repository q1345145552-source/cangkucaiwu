"""Compare original 94 findings with actual registered routes; intentional self/file exceptions stay explicit."""
from scripts.audit_management_access import audit, MANAGEMENT
from app.core.route_access import SELF_ROUTES, ACCOUNT_UTILITIES


def test_original94_registered_management_all_guarded():
    result=audit()
    # Round06 adds 5 scoped quote/version/recommendation routes after Round05.
    assert result['total_method_paths']==386
    assert result['management_method_paths']==363
    assert len(result['original94_comparison'])==94
    assert all(r['non_labor_guard'] and r['current_access'] in MANAGEMENT for r in result['original94_comparison'])
    assert result['unprotected_or_unclassified']==[]
    rows=result['routes']
    assert len({(r['method'],r['path']) for r in rows})==len(rows)
    for r in rows:
        if r['access'] in MANAGEMENT:
            assert r['non_labor_guard']
            assert 'require_business_user' in r['dependencies'] or 'require_office_user' in r['dependencies']
        elif r['access']=='employee_self_or_management':
            assert (r['module'],r['function']) in SELF_ROUTES and not r['non_labor_guard']
        elif r['access']=='account_utility':
            assert (r['module'],r['function']) in ACCOUNT_UTILITIES
        elif r['access']=='protected_attachment':
            assert r['path']=='/uploads/{file_path:path}'
        else:
            assert r['method']=='GET' and r['path'] in ('/','/health')


def test_inventory_includes_all_retired_endpoints_and_target_groups():
    result=audit();rows=result['routes']
    groups=set(result['management_by_module'])
    assert {'suppliers','income_expense','reimbursement','payable','credit','reports','cost_funds_debt',
        'market','group_order','exchange_rates','upload','sku_catalog','supplier_quotes','procurement_report'}<=groups
    retired={('GET','/api/v1/reports/operations'),('GET','/api/v1/customers/{customer_id}/receivables'),
        ('POST','/api/v1/customers/{customer_id}/receipts/link'),('GET','/api/v1/credit/shipments'),
        ('POST','/api/v1/credit/{credit_id}/shipment'),('PUT','/api/v1/credit/{credit_id}/shipment/{shipment_id}'),
        ('POST','/api/v1/credit/{credit_id}/shipment/{shipment_id}/void')}
    found={(r['method'],r['path']) for r in rows if 'require_operating_entries_enabled' in r['dependencies']}
    assert found==retired
    assert all(r['access']=='shared_platform' for r in rows if r['module'] in ('market','group_order'))
    new_details={('GET','/api/v1/payable/{bill_id}/detail'),('GET','/api/v1/suppliers/purchase-orders/{po_id}'),
        ('GET','/api/v1/suppliers/purchase-match-policy'),('PUT','/api/v1/suppliers/purchase-match-policy'),
        ('GET','/api/v1/suppliers/purchase-orders/{po_id}/receipts/{event_id}/photo'),
        ('GET','/api/v1/expense-identities/suppliers'),('GET','/api/v1/expense-identities/{source}/{source_id}')}
    assert new_details <= {(r['method'],r['path']) for r in rows if r['non_labor_guard'] and r['access']=='business_management'}
