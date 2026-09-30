import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.db import get_db
from app.models import Quality, Role, User
from app.schemas import EpisodePage
from app.services import episodes as episode_service
from app.services import importer

router = APIRouter(prefix="/episodes", tags=["episodes"])

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB, roughly 1.5 million rows


@router.get("/tasks", response_model=list[str])
def list_task_names(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Known task names. Any logged-in user: clients use it to pick a task that exists."""
    return episode_service.list_task_names(db)


@router.get("", response_model=EpisodePage)
def list_episodes(
    task_name: str | None = None,
    quality: Quality | None = None,
    robot_id: str | None = None,
    unassigned_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.operator, Role.admin)),
):
    items, total = episode_service.list_episodes(
        db,
        task_name=task_name,
        quality=quality,
        robot_id=robot_id,
        unassigned_only=unassigned_only,
        limit=limit,
        offset=offset,
    )
    return EpisodePage(items=items, total=total, limit=limit, offset=offset)


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
