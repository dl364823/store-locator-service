"""
Idempotent seed script.
Run from the project root:  python scripts/seed.py
Re-running is safe — existing records are skipped or updated.
"""
import csv
import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Allow running from the project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.db.models import Store, StoreService, Role, Permission, User
from app.services.auth import hash_password

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Permission names — single source of truth for role/permission seeding        #
# --------------------------------------------------------------------------- #
ALL_PERMISSIONS = [
    "stores:read",
    "stores:write",
    "users:read",
    "users:write",
    "import:write",
]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin":    ["stores:read", "stores:write", "users:read", "users:write", "import:write"],
    "marketer": ["stores:read", "stores:write", "import:write"],
    "viewer":   ["stores:read"],
}

SEED_USERS = [
    {"user_id": "U001", "email": "admin@test.com",    "password": "AdminTest123!",    "role": "admin"},
    {"user_id": "U002", "email": "marketer@test.com", "password": "MarketerTest123!", "role": "marketer"},
    {"user_id": "U003", "email": "viewer@test.com",   "password": "ViewerTest123!",   "role": "viewer"},
]

CSV_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _get_or_create_role(db: Session, name: str) -> Role:
    role = db.query(Role).filter_by(name=name).first()
    if not role:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def _get_or_create_permission(db: Session, name: str) -> Permission:
    perm = db.query(Permission).filter_by(name=name).first()
    if not perm:
        perm = Permission(name=name)
        db.add(perm)
        db.flush()
    return perm


# --------------------------------------------------------------------------- #
# Seed functions (each is independently callable for testing)                  #
# --------------------------------------------------------------------------- #

def seed_roles_and_permissions(db: Session) -> dict[str, Role]:
    """Create roles and permissions, assign permissions to roles. Idempotent."""
    perm_map: dict[str, Permission] = {}
    for perm_name in ALL_PERMISSIONS:
        perm_map[perm_name] = _get_or_create_permission(db, perm_name)

    role_map: dict[str, Role] = {}
    for role_name, perm_names in ROLE_PERMISSIONS.items():
        role = _get_or_create_role(db, role_name)
        existing_ids = {p.id for p in role.permissions}
        for perm_name in perm_names:
            perm = perm_map[perm_name]
            if perm.id not in existing_ids:
                role.permissions.append(perm)
        role_map[role_name] = role

    db.flush()
    return role_map


def seed_users(db: Session, role_map: dict[str, Role]) -> None:
    """Create the three seed users if they don't already exist."""
    for data in SEED_USERS:
        if db.query(User).filter_by(user_id=data["user_id"]).first():
            continue
        user = User(
            user_id=data["user_id"],
            email=data["email"],
            password_hash=hash_password(data["password"]),
            role_id=role_map[data["role"]].id,
            status="active",
            must_change_password=True,
        )
        db.add(user)
    db.flush()


def upsert_store(db: Session, row: dict) -> None:
    """Insert or update a single store row and replace its service entries."""
    store_id = row["store_id"]
    raw_services = row.get("services", "")
    services = [s.strip() for s in raw_services.split("|") if s.strip()]

    hours = {f"hours_{day}": (row.get(f"hours_{day}") or None) for day in CSV_DAYS}

    store = db.query(Store).filter_by(store_id=store_id).first()
    store_fields = dict(
        store_id=store_id,
        name=row["name"],
        store_type=row["store_type"],
        status=row["status"],
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        address_street=row["address_street"],
        address_city=row["address_city"],
        address_state=row["address_state"],
        address_postal_code=row["address_postal_code"],
        address_country=row["address_country"],
        phone=row["phone"],
        **hours,
    )

    if store:
        for key, value in store_fields.items():
            setattr(store, key, value)
    else:
        store = Store(**store_fields)
        db.add(store)

    db.flush()

    # Replace services atomically so re-seeding reflects CSV changes
    db.query(StoreService).filter_by(store_id=store_id).delete(synchronize_session=False)
    for svc in services:
        db.add(StoreService(store_id=store_id, service_name=svc))
    db.flush()


def seed_stores(db: Session, csv_path: Path) -> int:
    """Load all stores from a CSV file. Returns number of rows processed."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            upsert_store(db, row)
            count += 1
    return count


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    settings = get_settings()
    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()

    try:
        logger.info("Seeding roles and permissions…")
        role_map = seed_roles_and_permissions(db)

        logger.info("Seeding users…")
        seed_users(db, role_map)

        csv_path = Path(__file__).parent.parent / "stores_50.csv"
        logger.info("Seeding stores from %s…", csv_path)
        count = seed_stores(db, csv_path)

        db.commit()
        logger.info(
            "Done. Seeded %d stores, %d users, %d roles.",
            count, len(SEED_USERS), len(ROLE_PERMISSIONS),
        )
    except Exception:
        db.rollback()
        logger.exception("Seed failed — rolled back.")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
