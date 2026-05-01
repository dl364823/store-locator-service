import logging

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import User
from app.dependencies.rbac import require_permission
from app.exceptions import ValidationError
from app.schemas.import_schema import ImportReport
from app.services.csv_import import process_import

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin — Import"])

_ACCEPTED_CONTENT_TYPES = {"text/csv", "application/csv", "text/plain", "application/octet-stream"}


def _validate_file_type(file: UploadFile) -> None:
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    filename = (file.filename or "").lower()

    is_csv_name = filename.endswith(".csv")
    is_csv_type = content_type in _ACCEPTED_CONTENT_TYPES

    # Accept if either the filename or content-type suggests CSV.
    # This handles browser quirks where .csv files may be sent as text/plain.
    if not is_csv_name and not is_csv_type:
        raise ValidationError(
            f"File must be a CSV file (got content-type '{file.content_type}', "
            f"filename '{file.filename}'). Please upload a .csv file.",
            code="INVALID_FILE_TYPE",
        )


@router.post(
    "/stores/import",
    response_model=ImportReport,
    summary="Batch CSV import (upsert)",
    description=(
        "Upload a CSV file to create or update stores in bulk. "
        "The import is all-or-nothing: if any row fails validation, "
        "nothing is written to the database."
    ),
)
async def import_stores(
    file: UploadFile = File(..., description="CSV file with store data"),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("import:write")),
) -> ImportReport:
    _validate_file_type(file)

    content = await file.read()
    if not content:
        raise ValidationError("Uploaded file is empty.", code="EMPTY_FILE")

    logger.info(
        "CSV import started by user, file='%s', size=%d bytes",
        file.filename,
        len(content),
    )
    return process_import(db, content, filename=file.filename or "")
