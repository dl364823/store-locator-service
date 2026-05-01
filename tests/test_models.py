"""Verify model structure — no DB connection required."""
from app.db.base import Base
from app.db.models import Store, StoreService, Role, Permission, User, RefreshToken


def test_all_tables_registered():
    tables = set(Base.metadata.tables.keys())
    expected = {"stores", "store_services", "roles", "permissions", "role_permissions", "users", "refresh_tokens"}
    assert expected == tables


def test_store_required_indexes():
    store_table = Base.metadata.tables["stores"]
    index_names = {idx.name for idx in store_table.indexes}
    assert "ix_stores_lat_lon" in index_names
    assert "ix_stores_status_active" in index_names
    assert "ix_stores_store_type" in index_names
    assert "ix_stores_postal_code" in index_names


def test_user_email_index():
    user_table = Base.metadata.tables["users"]
    index_names = {idx.name for idx in user_table.indexes}
    assert "ix_users_email" in index_names


def test_refresh_token_hash_index():
    token_table = Base.metadata.tables["refresh_tokens"]
    index_names = {idx.name for idx in token_table.indexes}
    assert "ix_refresh_tokens_token_hash" in index_names


def test_store_columns():
    cols = {c.name for c in Base.metadata.tables["stores"].columns}
    required = {
        "store_id", "name", "store_type", "status",
        "latitude", "longitude",
        "address_street", "address_city", "address_state",
        "address_postal_code", "address_country",
        "phone",
        "hours_mon", "hours_tue", "hours_wed", "hours_thu",
        "hours_fri", "hours_sat", "hours_sun",
        "created_at", "updated_at",
    }
    assert required.issubset(cols)


def test_store_services_unique_constraint():
    table = Base.metadata.tables["store_services"]
    constraint_names = {c.name for c in table.constraints}
    assert "uq_store_service" in constraint_names


def test_refresh_token_stores_hash_not_raw():
    """Column is named token_hash — never the raw token."""
    cols = {c.name for c in Base.metadata.tables["refresh_tokens"].columns}
    assert "token_hash" in cols
    assert "token" not in cols  # raw token must never be stored


def test_user_has_must_change_password():
    cols = {c.name for c in Base.metadata.tables["users"].columns}
    assert "must_change_password" in cols


def test_role_permissions_junction_has_correct_fks():
    table = Base.metadata.tables["role_permissions"]
    fk_targets = {fk.target_fullname for fk in table.foreign_keys}
    assert "roles.id" in fk_targets
    assert "permissions.id" in fk_targets
