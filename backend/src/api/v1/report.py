"""
Report Generation API — stream report creation and download PDFs.
"""

import logging
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from typing import Optional

logger = logging.getLogger(__name__)

from src.services.report_service import report_service

router = APIRouter()


class ReportRequest(BaseModel):
    topic: str
    focus_mode: str = "all"


@router.post("/stream")
async def report_stream(request: ReportRequest):
    """Generate a professional PDF report. Streams SSE events showing live progress."""
    if not request.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    try:
        return StreamingResponse(
            report_service.stream_report(request.topic, request.focus_mode),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        logger.error(f"Error in report stream: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{report_id}")
async def download_report(report_id: str):
    """Download a generated PDF report."""
    filepath = report_service.get_report_path(report_id)
    if not filepath:
        raise HTTPException(status_code=404, detail="Report not found or expired")

    return FileResponse(
        path=filepath,
        media_type="application/pdf",
        filename=f"corten_report_{report_id}.pdf",
        headers={"Content-Disposition": f'attachment; filename="corten_report_{report_id}.pdf"'},
    )
