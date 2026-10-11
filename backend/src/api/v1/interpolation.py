"""Stateless interpolation upload, review and export endpoints."""
from enum import Enum
from threading import BoundedSemaphore

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from src.services.interpolation import (
    Encoding, InputLimitError, MAX_UPLOAD_BYTES, Mode, calculate, monthly_csv, read_csv,
)

router = APIRouter()
_capacity = BoundedSemaphore(1)


class OutputFormat(str, Enum):
    csv = "csv"
    json = "json"
    pdf = "pdf"


async def uploaded(file: UploadFile):
    try:
        if not file.filename or not file.filename.lower().endswith(".csv"):
            raise HTTPException(400, "Choose a file with a .csv extension.")
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "CSV files must be no larger than 10 MB.")
        return content
    finally:
        await file.close()


def operation(content, encoding, mode=None, output_format=None, expected=None):
    if not _capacity.acquire(blocking=False):
        raise HTTPException(503, "The calculation service is busy. Please retry in a few seconds.", headers={"Retry-After": "3"})
    try:
        data = read_csv(content, encoding)
        if mode is None:
            return JSONResponse(data.preview(), headers={"Cache-Control": "no-store"})
        result = calculate(data, mode)
        if expected and expected != result["calculation_id"]:
            raise HTTPException(409, "The calculation differs from the reviewed result. Generate the monthly series again before exporting.")
        headers = {"Cache-Control": "no-store", "X-Calculation-Engine": result["engine"]["id"]}
        if output_format is None:
            return JSONResponse(result, headers=headers)
        headers["Content-Disposition"] = f'attachment; filename="monthly-{mode.value}.{output_format.value}"'
        if output_format == OutputFormat.csv:
            return Response(monthly_csv(result), media_type="text/csv; charset=utf-8", headers=headers)
        if output_format == OutputFormat.json:
            return JSONResponse(result, headers=headers)
        from src.services.interpolation_pdf import build_pdf
        return Response(build_pdf(result), media_type="application/pdf", headers=headers)
    except InputLimitError as exc:
        raise HTTPException(413, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    finally:
        _capacity.release()


@router.post("/preview")
async def preview(file: UploadFile = File(...), encoding: Encoding = Query(Encoding.auto)):
    content = await uploaded(file)
    return await run_in_threadpool(operation, content, encoding)


@router.post("/calculate")
async def conversion(file: UploadFile = File(...), mode: Mode = Query(...), encoding: Encoding = Query(Encoding.auto)):
    content = await uploaded(file)
    return await run_in_threadpool(operation, content, encoding, mode)


@router.post("/export")
async def export(file: UploadFile = File(...), mode: Mode = Query(...),
                 format: OutputFormat = Query(...), encoding: Encoding = Query(Encoding.auto),
                 calculation_id: str | None = Query(None, pattern=r"^[a-f0-9]{64}$")):
    content = await uploaded(file)
    return await run_in_threadpool(operation, content, encoding, mode, format, calculation_id)
