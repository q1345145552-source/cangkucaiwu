"""Shared read-only predicate for boss todos and the filtered overtime list."""
from sqlalchemy import and_, or_
from app.models.overtime import OvertimeTask, OvertimeAssignment


def pending_overtime_assignment():
    return and_(OvertimeAssignment.confirmed == False,
                or_(OvertimeAssignment.actual_hours.is_(None), OvertimeAssignment.has_dispute == True))


def pending_overtime_task():
    return and_(OvertimeTask.needs_verification == True, OvertimeTask.status != "completed")
