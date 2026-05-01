"""Tests for seed helpers. Uses the SQLite in-memory DB from conftest."""
from pathlib import Path

import bcrypt
import pytest

from app.db.models import Role, Permission, User, Store, StoreService
from scripts.seed import (
    hash_password,
    seed_roles_and_permissions,
    seed_users,
    seed_stores,
    upsert_store,
    ROLE_PERMISSIONS,
    SEED_USERS,
    ALL_PERMISSIONS,
)

STORES_50_CSV = Path(__file__).parent.parent / "stores_50.csv"


# --------------------------------------------------------------------------- #
# hash_password                                                                #
# --------------------------------------------------------------------------- #

def test_hash_password_is_not_plaintext():
    hashed = hash_password("TestPassword123!")
    assert hashed != "TestPassword123!"


def test_hash_password_is_valid_bcrypt():
    password = "TestPassword123!"
    hashed = hash_password(password)
    assert bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def test_hash_password_unique_each_call():
    """bcrypt salts must produce different hashes for the same input."""
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2


# --------------------------------------------------------------------------- #
# seed_roles_and_permissions                                                   #
# --------------------------------------------------------------------------- #

def test_all_roles_created(db_session):
    seed_roles_and_permissions(db_session)
    db_session.commit()
    roles = {r.name for r in db_session.query(Role).all()}
    assert roles == set(ROLE_PERMISSIONS.keys())


def test_all_permissions_created(db_session):
    seed_roles_and_permissions(db_session)
    db_session.commit()
    perms = {p.name for p in db_session.query(Permission).all()}
    assert perms == set(ALL_PERMISSIONS)


def test_admin_has_all_permissions(db_session):
    role_map = seed_roles_and_permissions(db_session)
    db_session.commit()
    admin = role_map["admin"]
    db_session.refresh(admin)
    perm_names = {p.name for p in admin.permissions}
    assert perm_names == set(ROLE_PERMISSIONS["admin"])


def test_viewer_has_only_stores_read(db_session):
    role_map = seed_roles_and_permissions(db_session)
    db_session.commit()
    viewer = role_map["viewer"]
    db_session.refresh(viewer)
    assert {p.name for p in viewer.permissions} == {"stores:read"}


def test_marketer_cannot_manage_users(db_session):
    role_map = seed_roles_and_permissions(db_session)
    db_session.commit()
    marketer = role_map["marketer"]
    db_session.refresh(marketer)
    perm_names = {p.name for p in marketer.permissions}
    assert "users:write" not in perm_names
    assert "users:read" not in perm_names


def test_roles_idempotent(db_session):
    """Running seed twice must not create duplicate rows."""
    seed_roles_and_permissions(db_session)
    db_session.commit()
    seed_roles_and_permissions(db_session)
    db_session.commit()
    assert db_session.query(Role).count() == len(ROLE_PERMISSIONS)
    assert db_session.query(Permission).count() == len(ALL_PERMISSIONS)


# --------------------------------------------------------------------------- #
# seed_users                                                                   #
# --------------------------------------------------------------------------- #

def test_three_users_created(db_session):
    role_map = seed_roles_and_permissions(db_session)
    seed_users(db_session, role_map)
    db_session.commit()
    assert db_session.query(User).count() == len(SEED_USERS)


def test_user_passwords_are_hashed(db_session):
    role_map = seed_roles_and_permissions(db_session)
    seed_users(db_session, role_map)
    db_session.commit()
    for seed in SEED_USERS:
        user = db_session.query(User).filter_by(user_id=seed["user_id"]).one()
        assert user.password_hash != seed["password"]
        assert bcrypt.checkpw(seed["password"].encode(), user.password_hash.encode())


def test_users_must_change_password_on_first_login(db_session):
    role_map = seed_roles_and_permissions(db_session)
    seed_users(db_session, role_map)
    db_session.commit()
    for user in db_session.query(User).all():
        assert user.must_change_password is True


def test_users_have_correct_roles(db_session):
    role_map = seed_roles_and_permissions(db_session)
    seed_users(db_session, role_map)
    db_session.commit()
    for seed in SEED_USERS:
        user = db_session.query(User).filter_by(user_id=seed["user_id"]).one()
        assert user.role.name == seed["role"]


def test_users_idempotent(db_session):
    role_map = seed_roles_and_permissions(db_session)
    seed_users(db_session, role_map)
    db_session.commit()
    seed_users(db_session, role_map)
    db_session.commit()
    assert db_session.query(User).count() == len(SEED_USERS)


# --------------------------------------------------------------------------- #
# upsert_store / seed_stores                                                   #
# --------------------------------------------------------------------------- #

SAMPLE_ROW = {
    "store_id": "TEST01",
    "name": "Test Store",
    "store_type": "regular",
    "status": "active",
    "latitude": "42.3555",
    "longitude": "-71.0602",
    "address_street": "1 Main St",
    "address_city": "Boston",
    "address_state": "MA",
    "address_postal_code": "02101",
    "address_country": "USA",
    "phone": "617-555-0100",
    "services": "pharmacy|pickup",
    "hours_mon": "08:00-22:00",
    "hours_tue": "08:00-22:00",
    "hours_wed": "08:00-22:00",
    "hours_thu": "08:00-22:00",
    "hours_fri": "08:00-22:00",
    "hours_sat": "09:00-21:00",
    "hours_sun": "10:00-20:00",
}


def test_upsert_creates_store(db_session):
    upsert_store(db_session, SAMPLE_ROW)
    db_session.commit()
    store = db_session.query(Store).filter_by(store_id="TEST01").one()
    assert store.name == "Test Store"


def test_upsert_creates_services(db_session):
    upsert_store(db_session, SAMPLE_ROW)
    db_session.commit()
    svcs = {s.service_name for s in db_session.query(StoreService).filter_by(store_id="TEST01").all()}
    assert svcs == {"pharmacy", "pickup"}


def test_upsert_replaces_services_on_rerun(db_session):
    upsert_store(db_session, SAMPLE_ROW)
    db_session.commit()

    updated = {**SAMPLE_ROW, "services": "returns|optical"}
    upsert_store(db_session, updated)
    db_session.commit()

    svcs = {s.service_name for s in db_session.query(StoreService).filter_by(store_id="TEST01").all()}
    assert svcs == {"returns", "optical"}
    assert "pharmacy" not in svcs


def test_upsert_handles_empty_services(db_session):
    row = {**SAMPLE_ROW, "services": ""}
    upsert_store(db_session, row)
    db_session.commit()
    count = db_session.query(StoreService).filter_by(store_id="TEST01").count()
    assert count == 0


def test_upsert_updates_existing_store(db_session):
    upsert_store(db_session, SAMPLE_ROW)
    db_session.commit()

    updated = {**SAMPLE_ROW, "name": "Updated Store Name", "status": "inactive"}
    upsert_store(db_session, updated)
    db_session.commit()

    store = db_session.query(Store).filter_by(store_id="TEST01").one()
    assert store.name == "Updated Store Name"
    assert store.status == "inactive"
    assert db_session.query(Store).count() == 1  # no duplicate row


def test_upsert_stores_only_one_row_per_store_id(db_session):
    upsert_store(db_session, SAMPLE_ROW)
    upsert_store(db_session, SAMPLE_ROW)
    db_session.commit()
    assert db_session.query(Store).filter_by(store_id="TEST01").count() == 1


@pytest.mark.skipif(
    not STORES_50_CSV.exists(),
    reason="stores_50.csv not present",
)
def test_seed_stores_loads_50_rows(db_session):
    count = seed_stores(db_session, STORES_50_CSV)
    db_session.commit()
    assert count == 50
    assert db_session.query(Store).count() == 50


@pytest.mark.skipif(
    not STORES_50_CSV.exists(),
    reason="stores_50.csv not present",
)
def test_seed_stores_idempotent(db_session):
    seed_stores(db_session, STORES_50_CSV)
    db_session.commit()
    seed_stores(db_session, STORES_50_CSV)
    db_session.commit()
    assert db_session.query(Store).count() == 50


def test_seed_stores_raises_on_missing_file(db_session):
    with pytest.raises(FileNotFoundError):
        seed_stores(db_session, Path("/nonexistent/path.csv"))
