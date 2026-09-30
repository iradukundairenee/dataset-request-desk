import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models import Role, User
from app.services import importer

router = APIRouter(prefix="/episodes", tags=["episodes"])

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB, roughly 1.5 million rows


@router.post(
    "/import",
    # The CSV is sent as the raw request body (Content-Type: text/csv). This tells
    # the /docs page to show a text box for it.
    openapi_extra={"requestBody": {"required": True, "content": {"text/csv": {"schema": {"type": "string"}}}}},
)
async def import_episodes(
    request: Request,
    filename: str = "upload.csv",
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.operator, Role.admin)),
):
    # Stream the body to a temp file: the importer reads the file twice and
    # never holds it all in memory.
    size = 0
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        try:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File is larger than 100 MB")
                tmp.write(chunk)
        except HTTPException:
            os.unlink(tmp.name)
            raise
    try:
        # The import is blocking database work; run it off the event loop.
        return await run_in_threadpool(importer.import_file, db, tmp.name, filename, user.id)
    finally:
        os.unlink(tmp.name)
