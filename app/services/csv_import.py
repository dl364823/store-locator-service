"""
CSV batch import service.

Strategy:
  1. Validate the file (encoding, content type, size).
  2. Validate all headers.
  3. Validate every row, collecting ALL errors.
  4. If any errors → return error report, commit NOTHING.
  5. If all valid → run all upserts in a single transaction and commit.
"""
import csv
import io
import logging
import re

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Store, StoreService
from app.exceptions import ValidationError
from app.schemas.import_schema import ImportReport, ImportRowError
from app.services.geocoding import geocode_address
from app.services.hours import validate_hours_string

logger = logging.getLogger(__name__)

_PHONE_RE = re.compile(r"^\d{3}-\d{3}-\d{4}$")
_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

REQUIRED_HEADERS = [
    "store_id", "name", "store_type", "status",
    "latitude", "longitude",
    "address_street", "address_city", "address_state",
    "address_postal_code", "address_country",
    "phone", "services",
    "hours_mon", "hours_tue", "hours_wed", "hours_thu",
    "hours_fri", "hours_sat", "hours_sun",
]


# ---------- Row validation ----------

def _collect_row_errors(row: dict) -> list[str]:
    """Return a list of human-readable error strings for a single CSV row."""
    errors: list[str] = []
    settings = get_settings()

    # store_id
    sid = row.get("store_id", "").strip()
    if not sid:
        errors.append("store_id is required")
    elif len(sid) > 10:
        errors.append(f"store_id '{sid}' exceeds 10 characters")

    # name
    name = row.get("name", "").strip()
    if not name:
        errors.append("name is required")
    elif len(name) > 255:
        errors.append("name exceeds 255 characters")

    # store_type
    st = row.get("store_type", "").strip()
    if st not in settings.allowed_store_types:
        errors.append(f"store_type '{st}' is invalid. Allowed: {settings.allowed_store_types}")

    # status
    status = row.get("status", "").strip()
    if status not in settings.allowed_store_statuses:
        errors.append(f"status '{status}' is invalid. Allowed: {settings.allowed_store_statuses}")

    # latitude / longitude — both present or both absent
    lat_str = row.get("latitude", "").strip()
    lon_str = row.get("longitude", "").strip()
    lat = lon = None

    if lat_str:
        try:
            lat = float(lat_str)
            if not -90 <= lat <= 90:
                errors.append(f"latitude {lat} is out of range [-90, 90]")
                lat = None
        except ValueError:
            errors.append(f"latitude '{lat_str}' is not a valid number")

    if lon_str:
        try:
            lon = float(lon_str)
            if not -180 <= lon <= 180:
                errors.append(f"longitude {lon} is out of range [-180, 180]")
                lon = None
        except ValueError:
            errors.append(f"longitude '{lon_str}' is not a valid number")

    if bool(lat_str) != bool(lon_str):
        errors.append("latitude and longitude must both be provided or both be empty")

    # required address fields
    for field in ("address_street", "address_city", "address_state", "address_country"):
        if not row.get(field, "").strip():
            errors.append(f"{field} is required")

    state = row.get("address_state", "").strip()
    if state and len(state) != 2:
        errors.append(f"address_state must be a 2-letter code, got '{state}'")

    postal = row.get("address_postal_code", "").strip()
    if not re.match(r"^\d{5}$", postal):
        errors.append(f"address_postal_code '{postal}' must be a 5-digit ZIP")

    # phone
    phone = row.get("phone", "").strip()
    if not _PHONE_RE.match(phone):
        errors.append(f"phone '{phone}' must match XXX-XXX-XXXX")

    # services
    svcs_raw = row.get("services", "").strip()
    if svcs_raw:
        svcs = [s.strip() for s in svcs_raw.split("|") if s.strip()]
        bad = [s for s in svcs if s not in settings.allowed_services]
        if bad:
            errors.append(f"Invalid services: {bad}. Allowed: {settings.allowed_services}")

    # hours
    for day in _DAYS:
        val = row.get(f"hours_{day}", "").strip()
        if val and not validate_hours_string(val):
            errors.append(
                f"hours_{day}: invalid value '{val}'. "
                "Use 'closed' or 'HH:MM-HH:MM' with close time > open time."
            )

    return errors


# ---------- Upsert (called only after all rows pass validation) ----------

def _upsert_row(db: Session, row: dict) -> str:
    """Upsert one validated row. Returns 'created' or 'updated'."""
    store_id = row["store_id"].strip()
    lat_str = row.get("latitude", "").strip()
    lon_str = row.get("longitude", "").strip()

    lat = float(lat_str) if lat_str else None
    lon = float(lon_str) if lon_str else None

    if lat is None:
        address = (
            f"{row['address_street'].strip()}, "
            f"{row['address_city'].strip()}, "
            f"{row['address_state'].strip()} "
            f"{row['address_postal_code'].strip()}"
        )
        lat, lon = geocode_address(address)

    hours = {
        f"hours_{day}": (row.get(f"hours_{day}", "").strip() or None)
        for day in _DAYS
    }
    svcs_raw = row.get("services", "").strip()
    services = [s.strip() for s in svcs_raw.split("|") if s.strip()]

    store_fields = dict(
        store_id=store_id,
        name=row["name"].strip(),
        store_type=row["store_type"].strip(),
        status=row["status"].strip(),
        latitude=lat,
        longitude=lon,
        address_street=row["address_street"].strip(),
        address_city=row["address_city"].strip(),
        address_state=row["address_state"].strip(),
        address_postal_code=row["address_postal_code"].strip(),
        address_country=row["address_country"].strip(),
        phone=row["phone"].strip(),
        **hours,
    )

    existing = db.query(Store).filter_by(store_id=store_id).first()
    if existing:
        for k, v in store_fields.items():
            setattr(existing, k, v)
        action = "updated"
    else:
        db.add(Store(**store_fields))
        action = "created"

    db.flush()

    db.query(StoreService).filter_by(store_id=store_id).delete(synchronize_session=False)
    for svc in services:
        db.add(StoreService(store_id=store_id, service_name=svc))
    db.flush()

    return action


# ---------- Main entry point ----------

def process_import(db: Session, content: bytes, filename: str = "") -> ImportReport:
    # Decode
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise ValidationError("File must be UTF-8 encoded.", code="ENCODING_ERROR")

    if not text.strip():
        raise ValidationError("File is empty.", code="EMPTY_FILE")

    reader = csv.DictReader(io.StringIO(text))

    # Header validation
    if reader.fieldnames is None:
        raise ValidationError("File has no recognisable headers.", code="MISSING_HEADERS")

    actual = list(reader.fieldnames)
    missing = [h for h in REQUIRED_HEADERS if h not in actual]
    if missing:
        raise ValidationError(
            f"Missing required columns: {missing}", code="MISSING_HEADERS"
        )

    # Read rows eagerly so we can report the count even on error
    try:
        rows = list(reader)
    except csv.Error as exc:
        raise ValidationError(f"CSV parse error: {exc}", code="CSV_PARSE_ERROR")

    if not rows:
        raise ValidationError(
            "File contains headers only — no data rows found.", code="NO_DATA_ROWS"
        )

    # Validate all rows; collect every error before touching the DB
    all_errors: list[ImportRowError] = []
    seen_ids: set[str] = set()

    for i, row in enumerate(rows, start=2):  # row 1 = headers
        sid = row.get("store_id", "").strip()

        if sid and sid in seen_ids:
            all_errors.append(ImportRowError(
                row=i, store_id=sid,
                message=f"Duplicate store_id '{sid}' within this CSV file",
            ))
        else:
            seen_ids.add(sid)

        for msg in _collect_row_errors(row):
            all_errors.append(ImportRowError(row=i, store_id=sid or None, message=msg))

    if all_errors:
        return ImportReport(
            total=len(rows),
            created=0,
            updated=0,
            failed=len({e.row for e in all_errors}),
            errors=all_errors,
            success=False,
        )

    # All rows valid — single transaction
    created = updated = 0
    try:
        for row in rows:
            action = _upsert_row(db, row)
            if action == "created":
                created += 1
            else:
                updated += 1
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Unexpected error during CSV import transaction")
        raise

    logger.info("CSV import complete: %d created, %d updated", created, updated)
    return ImportReport(
        total=len(rows),
        created=created,
        updated=updated,
        failed=0,
        errors=[],
        success=True,
    )
