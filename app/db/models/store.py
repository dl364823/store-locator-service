from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Store(Base):
    __tablename__ = "stores"

    store_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    store_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    latitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    address_street: Mapped[str] = mapped_column(String(255), nullable=False)
    address_city: Mapped[str] = mapped_column(String(100), nullable=False)
    address_state: Mapped[str] = mapped_column(String(2), nullable=False)
    address_postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    address_country: Mapped[str] = mapped_column(String(3), nullable=False, default="USA")
    phone: Mapped[str] = mapped_column(String(20), nullable=False)

    # Operating hours: "HH:MM-HH:MM" or "closed"; NULL means not specified
    hours_mon: Mapped[str | None] = mapped_column(String(20))
    hours_tue: Mapped[str | None] = mapped_column(String(20))
    hours_wed: Mapped[str | None] = mapped_column(String(20))
    hours_thu: Mapped[str | None] = mapped_column(String(20))
    hours_fri: Mapped[str | None] = mapped_column(String(20))
    hours_sat: Mapped[str | None] = mapped_column(String(20))
    hours_sun: Mapped[str | None] = mapped_column(String(20))

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    services: Mapped[list["StoreService"]] = relationship(
        "StoreService", back_populates="store", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Composite index for bounding-box geographic queries
        Index("ix_stores_lat_lon", "latitude", "longitude"),
        # Partial index — only indexes active stores, keeping it small and fast
        Index(
            "ix_stores_status_active",
            "status",
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_stores_store_type", "store_type"),
        Index("ix_stores_postal_code", "address_postal_code"),
    )


class StoreService(Base):
    __tablename__ = "store_services"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("stores.store_id", ondelete="CASCADE"),
        nullable=False,
    )
    service_name: Mapped[str] = mapped_column(String(50), nullable=False)

    store: Mapped["Store"] = relationship("Store", back_populates="services")

    __table_args__ = (
        UniqueConstraint("store_id", "service_name", name="uq_store_service"),
    )
