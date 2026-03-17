from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime


# ─── Token Schemas ────────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenPayload(BaseModel):
    sub: int  # user_id
    type: str
    exp: datetime


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ─── Auth Request Schemas ──────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


class PlantSelectRequest(BaseModel):
    plant_id: int


# ─── User Response Schemas ─────────────────────────────────────────────────────
class PlantBasic(BaseModel):
    id: int
    name: str
    code: str
    schema_name: str
    is_active: bool

    model_config = {"from_attributes": True}


class RoleBasic(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    role: RoleBasic
    is_active: bool
    is_superuser: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    token: Token
    user: UserResponse
    accessible_plants: list[PlantBasic]


# ─── Register (self-service) ───────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    full_name: str                   # wajib saat register
    password: str
    confirm_password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username minimal 3 karakter")
        if len(v) > 50:
            raise ValueError("Username maksimal 50 karakter")
        import re
        if not re.match(r"^[a-zA-Z0-9_.-]+$", v):
            raise ValueError("Username hanya boleh huruf, angka, titik, strip, dan underscore")
        return v

    @field_validator("full_name")
    @classmethod
    def full_name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nama lengkap tidak boleh kosong")
        if len(v) < 2:
            raise ValueError("Nama lengkap minimal 2 karakter")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        import re
        if len(v) < 8:
            raise ValueError("Password minimal 8 karakter")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password harus mengandung minimal 1 huruf kapital")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password harus mengandung minimal 1 angka")
        return v

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Konfirmasi password tidak cocok")
        return v


class RegisterResponse(BaseModel):
    message: str
    user: "UserResponse"


# ─── User Create / Update (by Admin) ──────────────────────────────────────────
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    full_name: str                   # wajib saat admin buat user
    password: str
    role_id: int
    plant_ids: list[int] = []

    @field_validator("full_name")
    @classmethod
    def full_name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nama lengkap tidak boleh kosong")
        return v

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password minimal 8 karakter")
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None
    plant_ids: Optional[list[int]] = None


# ─── Update Profile (self) ─────────────────────────────────────────────────────
class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None

    @field_validator("full_name")
    @classmethod
    def full_name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Nama lengkap tidak boleh kosong")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        import re
        if len(v) < 8:
            raise ValueError("Password baru minimal 8 karakter")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password harus mengandung minimal 1 huruf kapital")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password harus mengandung minimal 1 angka")
        return v

    @field_validator("confirm_new_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Konfirmasi password tidak cocok")
        return v