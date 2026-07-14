# models.py

from datetime import datetime

from sqlmodel import JSON, Column, Field, SQLModel, UniqueConstraint

from .utils import generate_csrf_token


class Users(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    role: str = Field(default="customer")  # "customer" | "admin"


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: int | None = Field(default=None, primary_key=True)
    token: str = Field(index=True, unique=True, max_length=64)
    csrf_token: str = Field(default_factory=generate_csrf_token)
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
