"""Read-only display metadata for existing, same-warehouse payment links."""
from sqlalchemy import select, tuple_
from app.models.cash_advance import CashAdvance


async def cash_advance_numbers(db, records):
    pairs = {(row.cash_advance_id, row.warehouse_id) for row in records if row.cash_advance_id is not None}
    if not pairs:
        return {}
    rows = (await db.execute(select(CashAdvance.id, CashAdvance.warehouse_id).where(
        tuple_(CashAdvance.id, CashAdvance.warehouse_id).in_(pairs),
    ))).all()
    # Existing screens identify an advance by #id; do not create another numbering scheme.
    return {(row.id, row.warehouse_id): f"#{row.id}" for row in rows}


def cash_advance_reference(row, numbers):
    return {"cash_advance_number": numbers.get((row.cash_advance_id, row.warehouse_id))}
