# models.py
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint


class Users(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    phone: str | None = Field(default=None)
    password_hash: str
    role: str = Field(default="customer")  # "customer" | "admin"
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    invoices: List["Invoice"] = Relationship(back_populates="user")


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
    image_url: List[str] = Field(default_factory=List, sa_column=Column(JSON))
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


class CartItem(SQLModel, table=True):
    __tablename__ = "cart_items"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    quantity: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Invoice(SQLModel, table=True):
    __tablename__ = "invoices"
    id: int = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    invoice_number: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    items: List[dict] = Field(default=[], sa_column=Column(JSON))
    subtotal: float
    delivery_fee: float = 0.0
    total: float
    payment_method: str  # 'transfer' or 'pickup'
    delivery_method: str  # 'delivery' or 'pickup'
    delivery_location: str | None = None
    delivery_note: str | None = None
    status: str = "pending"  # pending, paid, etc.

    # optional relationship back to user (not required for public view)
    user: Optional["Users"] = Relationship(back_populates="invoices")
