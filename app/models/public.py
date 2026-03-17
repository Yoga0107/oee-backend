"""
Public schema models.
These live in the default 'public' schema and are shared across all plants.
"""
from datetime import datetime
from sqlalchemy import (
    Integer, String, Boolean, DateTime, ForeignKey,
    UniqueConstraint, func, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "public"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    users: Mapped[list["User"]] = relationship("User", back_populates="role")


class Plant(Base):
    __tablename__ = "plants"
    __table_args__ = {"schema": "public"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    schema_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("public.users.id"))

    created_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[created_by_id]
    )
    user_plants: Mapped[list["UserPlant"]] = relationship("UserPlant", back_populates="plant")


# ... (import tetap sama)

class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "public"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("public.roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("public.users.id"), nullable=True
    )

    role: Mapped["Role"] = relationship("Role", back_populates="users")
    
    # Tambahkan overlaps="created_by" jika ada peringatan saat inisialisasi
    user_plants: Mapped[list["UserPlant"]] = relationship(
        "UserPlant", 
        back_populates="user", 
        foreign_keys="[UserPlant.user_id]"  # <--- Tegaskan pakai user_id
    )
    
    created_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[created_by_id], remote_side="User.id"
    )


class UserPlant(Base):
    """Junction table: which user has access to which plant."""
    __tablename__ = "user_plants"
    __table_args__ = (
        UniqueConstraint("user_id", "plant_id", name="uq_user_plant"),
        {"schema": "public"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("public.users.id"), nullable=False)
    plant_id: Mapped[int] = mapped_column(Integer, ForeignKey("public.plants.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("public.users.id"), nullable=True
    )

    # PERBAIKAN DI SINI:
    user: Mapped["User"] = relationship(
        "User", 
        foreign_keys=[user_id],           # <--- Kunci utama relasi
        back_populates="user_plants"
    )
    plant: Mapped["Plant"] = relationship("Plant", back_populates="user_plants")
    
    # Beri nama relasi yang berbeda agar tidak bentrok
    creator: Mapped["User | None"] = relationship(
        "User", 
        foreign_keys=[created_by_id]      # <--- Kunci audit
    )

# ... (RefreshToken tetap sama)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": "public"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("public.users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User")
