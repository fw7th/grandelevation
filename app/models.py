# models.py

from datetime import datetime

from sqlmodel import JSON, Column, Field, SQLModel


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
