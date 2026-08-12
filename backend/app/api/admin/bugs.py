"""The bug-report inbox: list what users filed, move a ticket along, drop it."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.deps import require_admin
from ...db import get_session
from ...models import BUG_REPORT_STATUSES, BugReport, User
from ...schemas import BugReporterOut, BugReportOut, BugReportStatusIn

router = APIRouter()


def _out(report: BugReport) -> BugReportOut:
    reporter = (
        BugReporterOut(
            id=report.user.id,
            email=report.user.email,
            display_name=report.user.display_name,
        )
        if report.user is not None
        else None
    )
    return BugReportOut(
        id=report.id,
        status=report.status,
        description=report.description,
        screenshot=report.screenshot,
        app_version=report.app_version,
        browser=report.browser,
        os=report.os,
        user_agent=report.user_agent,
        context=report.context or {},
        reporter=reporter,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


@router.get("/admin/bug-reports", response_model=list[BugReportOut])
async def admin_list_bug_reports(
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    stmt = select(BugReport).order_by(BugReport.created_at.desc()).limit(limit)
    if status:
        if status not in BUG_REPORT_STATUSES:
            raise HTTPException(status_code=400, detail="unknown status")
        stmt = stmt.where(BugReport.status == status)
    rows = (await session.execute(stmt)).unique().scalars().all()
    return [_out(r) for r in rows]


@router.patch("/admin/bug-reports/{report_id}", response_model=BugReportOut)
async def admin_set_bug_report_status(
    report_id: int,
    body: BugReportStatusIn,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    report = await session.get(BugReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="bug report not found")
    report.status = body.status
    await session.commit()
    await session.refresh(report)
    return _out(report)


@router.delete("/admin/bug-reports/{report_id}")
async def admin_delete_bug_report(
    report_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    report = await session.get(BugReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="bug report not found")
    await session.delete(report)
    await session.commit()
    return {"deleted": report_id}
