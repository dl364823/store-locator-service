from pydantic import BaseModel


class ImportRowError(BaseModel):
    row: int
    store_id: str | None
    message: str


class ImportReport(BaseModel):
    total: int
    created: int
    updated: int
    failed: int
    errors: list[ImportRowError]
    success: bool
