"""Initial schema: all tables and indexes

Revision ID: 001
Revises:
Create Date: 2026-05-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ stores
    op.create_table(
        "stores",
        sa.Column("store_id", sa.String(10), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("store_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("address_street", sa.String(255), nullable=False),
        sa.Column("address_city", sa.String(100), nullable=False),
        sa.Column("address_state", sa.String(2), nullable=False),
        sa.Column("address_postal_code", sa.String(10), nullable=False),
        sa.Column("address_country", sa.String(3), nullable=False, server_default="USA"),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("hours_mon", sa.String(20), nullable=True),
        sa.Column("hours_tue", sa.String(20), nullable=True),
        sa.Column("hours_wed", sa.String(20), nullable=True),
        sa.Column("hours_thu", sa.String(20), nullable=True),
        sa.Column("hours_fri", sa.String(20), nullable=True),
        sa.Column("hours_sat", sa.String(20), nullable=True),
        sa.Column("hours_sun", sa.String(20), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )

    # Composite geographic index for bounding-box pre-filter
    op.create_index("ix_stores_lat_lon", "stores", ["latitude", "longitude"])
    # Partial index — only active stores are queried in public search
    op.create_index(
        "ix_stores_status_active",
        "stores",
        ["status"],
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index("ix_stores_store_type", "stores", ["store_type"])
    op.create_index("ix_stores_postal_code", "stores", ["address_postal_code"])

    # ----------------------------------------------------------- store_services
    op.create_table(
        "store_services",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "store_id",
            sa.String(10),
            sa.ForeignKey("stores.store_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("service_name", sa.String(50), nullable=False),
        sa.UniqueConstraint("store_id", "service_name", name="uq_store_service"),
    )
    op.create_index("ix_store_services_store_id", "store_services", ["store_id"])

    # --------------------------------------------------------------- roles
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
    )

    # ----------------------------------------------------------- permissions
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
    )

    # -------------------------------------------------------- role_permissions
    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id",
            sa.Integer(),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_id",
            sa.Integer(),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # --------------------------------------------------------------- users
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(10), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "role_id",
            sa.Integer(),
            sa.ForeignKey("roles.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # --------------------------------------------------------- refresh_tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column(
            "user_id",
            sa.String(10),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("store_services")
    op.drop_index("ix_stores_postal_code", table_name="stores")
    op.drop_index("ix_stores_store_type", table_name="stores")
    op.drop_index("ix_stores_status_active", table_name="stores")
    op.drop_index("ix_stores_lat_lon", table_name="stores")
    op.drop_table("stores")
