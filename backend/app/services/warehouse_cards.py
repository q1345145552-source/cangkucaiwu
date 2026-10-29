"""Read-only cards for explicitly assigned warehouses, independent of active scope."""
from collections import defaultdict

from sqlalchemy import and_, func, literal, or_, select, union_all

from app.core.timezone import thai_today
from app.models import Employee, EmployeeAdvance, ExpenseFund, ExpenseFundItem, PayableBill, UserWarehouse, Warehouse
from app.models.attendance import LeaveRequest, RestDay
from app.models.attendance_exemption import AttendanceExemption
from app.models.clock_in_records import ClockInRecord
from app.models.expense_fund import FundRechargeRequest
from app.models.overtime import OvertimeAssignment, OvertimeTask
from app.models.supplier import PurchaseOrder
from app.services import wallet
from app.services.attendance_exemptions import valid_clock
from app.services.attendance_population import employee_account_roles, includes_efficiency
from app.services.boss_todos import pending_overtime_assignment, pending_overtime_task
from app.services.employee_match import resolve_employee_user_map


TODO_KEYS = ('employee_advances', 'overtime_employee_confirmation', 'overtime_admin_verification',
             'expense_fund_review', 'purchase_approval', 'receipt_review')


class _WarehouseGroupedTotals:
    """Keep totals' exact projection/filters/sum, adding only the warehouse dimension.

    totals normally merges its requested warehouses. This session adapter adds a
    group key to that very SELECT, so one call serves every card without N queries
    or a second implementation of wallet accounting.
    """
    def __init__(self, db):
        self.db, self.bind = db, db.bind

    async def execute(self, statement):
        warehouse = statement.get_final_froms()[0].c.warehouse_id
        return await self.db.execute(statement.add_columns(warehouse).group_by(warehouse))


async def cards(db, user):
    today = thai_today()
    warehouses = (await db.execute(select(Warehouse).join(UserWarehouse,
        UserWarehouse.warehouse_id == Warehouse.id).where(UserWarehouse.user_id == user.id,
        Warehouse.is_active.is_(True)).distinct().order_by(Warehouse.code, Warehouse.id))).scalars().all()
    if not warehouses:
        return {'date': today.isoformat(), 'timezone': 'Asia/Bangkok', 'data': []}
    ids = [w.id for w in warehouses]
    amounts = defaultdict(lambda: {'income': [], 'expense': []})
    for currency, kind, value, wid in await wallet.totals(_WarehouseGroupedTotals(db), ids, today, today):
        amounts[wid][kind].append({'currency': currency, 'amount': format(wallet.money(value), '.2f')})

    def count(wid, key, *conditions):
        return select(wid.label('warehouse_id'), literal(key).label('kind'), func.count().label('n')).where(
            wid.in_(ids), *conditions).group_by(wid)

    a, t = OvertimeAssignment, OvertimeTask
    overtime_join = and_(a.overtime_id == t.id, Employee.id == a.employee_id,
                        Employee.warehouse_id == t.warehouse_id)
    queries = [
        count(EmployeeAdvance.warehouse_id, 'employee_advances', EmployeeAdvance.not_voided(),
            EmployeeAdvance.approval_status.in_(['pending', 'verified']),
            Employee.id == EmployeeAdvance.employee_id, Employee.warehouse_id == EmployeeAdvance.warehouse_id),
        count(t.warehouse_id, 'overtime_employee_confirmation', overtime_join,
            a.confirmed.is_(False), a.has_dispute.is_not(True),
            or_(t.needs_verification.is_not(True), a.actual_hours.is_not(None))),
        count(t.warehouse_id, 'overtime_admin_verification', overtime_join,
            pending_overtime_task(), pending_overtime_assignment()),
        count(ExpenseFund.warehouse_id, 'expense_fund_review', ExpenseFundItem.fund_id == ExpenseFund.id,
            ExpenseFundItem.review_status == 'pending', ExpenseFundItem.not_voided()),
        count(FundRechargeRequest.warehouse_id, 'expense_fund_review',
            FundRechargeRequest.status == 'pending', FundRechargeRequest.fund_id == ExpenseFund.id,
            ExpenseFund.warehouse_id == FundRechargeRequest.warehouse_id),
        count(PurchaseOrder.warehouse_id, 'purchase_approval', PurchaseOrder.status == 'pending'),
        count(PayableBill.warehouse_id, 'receipt_review', PayableBill.status != 'voided',
            or_(PayableBill.need_boss_confirm == 'true', and_(PayableBill.confirmed_amount.is_not(None),
                PayableBill.confirmed_amount != PayableBill.amount))),
    ]
    todos = defaultdict(lambda: dict.fromkeys(TODO_KEYS, 0))
    for wid, key, n in (await db.execute(union_all(*queries))).all():
        todos[wid][key] += n

    employees = (await db.execute(select(Employee).where(Employee.warehouse_id.in_(ids),
        Employee.is_deleted.is_(False), Employee.status != 'resigned'))).scalars().all()
    owners, _ = await employee_account_roles(db, employees)
    population = [e for e in employees if includes_efficiency(e, owners.get(e.id))
        and (e.hire_date is None or e.hire_date.date() <= today)
        and (e.resignation_date is None or e.resignation_date > today)]
    employee_users, user_employees = await resolve_employee_user_map(db, population)
    # Different fact types share one batched round trip; no per-employee queries.
    facts = union_all(
        select(RestDay.warehouse_id, literal('rest'), RestDay.employee_id).where(
            RestDay.warehouse_id.in_(ids), RestDay.rest_date == today),
        select(LeaveRequest.warehouse_id, literal('leave'), LeaveRequest.employee_id).where(
            LeaveRequest.warehouse_id.in_(ids), LeaveRequest.leave_date == today,
            LeaveRequest.status == 'approved', or_(LeaveRequest.duration_type.in_(['full', '']),
                                                   LeaveRequest.duration_type.is_(None))),
        select(AttendanceExemption.warehouse_id, literal('exempt'), literal(0)).where(
            AttendanceExemption.warehouse_id.in_(ids), AttendanceExemption.date == today,
            AttendanceExemption.status == 'active'),
        select(ClockInRecord.warehouse_id, literal('clock'), ClockInRecord.user_id).where(
            ClockInRecord.warehouse_id.in_(ids), ClockInRecord.clock_date == today,
            ClockInRecord.session == 1, valid_clock()),
    )
    excluded, exempt, clocks = set(), set(), set()
    for wid, kind, person in (await db.execute(facts)).all():
        if kind == 'exempt':
            exempt.add(wid)
        elif kind == 'clock':
            clocks.add((wid, person))
        else:
            excluded.add((wid, person))
    attendance = defaultdict(lambda: {'expected': 0, 'actual': 0})
    for employee in population:
        wid = employee.warehouse_id
        if wid in exempt or (wid, employee.id) in excluded:
            continue
        attendance[wid]['expected'] += 1
        uid = employee_users.get(employee.id)
        if uid is not None and user_employees.get(uid) == employee.id and (wid, uid) in clocks:
            attendance[wid]['actual'] += 1

    flows = wallet.flow_query(db, ids)
    activity = union_all(select(Employee.warehouse_id).where(Employee.warehouse_id.in_(ids)),
        select(flows.c.warehouse_id), select(PurchaseOrder.warehouse_id).where(PurchaseOrder.warehouse_id.in_(ids))).subquery()
    populated = set((await db.execute(select(activity.c.warehouse_id).distinct())).scalars())
    return {'date': today.isoformat(), 'timezone': 'Asia/Bangkok', 'data': [
        {'warehouse_id': w.id, 'warehouse_name': w.name, 'warehouse_code': w.code,
         'income_by_currency': sorted(amounts[w.id]['income'], key=lambda v: v['currency']),
         'expense_by_currency': sorted(amounts[w.id]['expense'], key=lambda v: v['currency']),
         'todos': {**todos[w.id], 'total': sum(todos[w.id].values())},
         'attendance': attendance[w.id], 'has_data': w.id in populated}
        for w in warehouses]}
