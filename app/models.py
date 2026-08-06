# models.py
import enum
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel, UniqueConstraint


class Users(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    phone: str | None = Field(default=None)
    password_hash: str
    role: str = Field(default="customer")  # "customer" | "admin"


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: int | None = Field(default=None, primary_key=True)
    token: str = Field(index=True, unique=True, max_length=64)
    user_id: int = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime


class Product(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    category: str  # "panel" | "inverter" | "battery" | "accessory"
    name: str
    price: float
    description: str
    image_url: str | None = None
    specs: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class LoginAttempt(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str
    ip_address: str
    succeeded: bool
    attempted_at: datetime = Field(default_factory=datetime.utcnow)


class Favorite(SQLModel, table=True):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_favorite_user_product"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PasswordResetToken(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    token_hash: str
    expires_at: datetime = Field(
        default_factory=lambda: datetime.utcnow() + timedelta(hours=1)
    )
    used_at: datetime | None = Field(default=None)


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CartItem(SQLModel, table=True):
    __tablename__ = "cart_items"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    quantity: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Order(SQLModel, table=True):
    __tablename__ = "orders"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    status: OrderStatus = Field(default=OrderStatus.PENDING)
    total: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OrderItem(SQLModel, table=True):
    __tablename__ = "order_items"

    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", index=True)
    product_id: int = Field(foreign_key="product.id")
    quantity: int = Field(ge=1)
    unit_price: float  # snapshot at purchase time


class SavedSystem(SQLModel, table=True):
    __tablename__ = "saved_systems"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str | None = None
    configuration: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    total_price: float = Field(default=0.0)
    estimated_daily_wh: float | None = None
    estimated_peak_w: float | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
