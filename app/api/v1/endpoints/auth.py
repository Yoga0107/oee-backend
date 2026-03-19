from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from app.db.database import get_db
from app.core.security import (
    verify_password, create_access_token, create_refresh_token,
    decode_token, get_password_hash
)
from app.core.config import settings
from app.core.deps import CurrentUser, get_current_user
from app.models.public import User, Plant, UserPlant, RefreshToken
from app.schemas.auth import (
    LoginRequest, LoginResponse, Token, UserResponse,
    PlantBasic, RefreshTokenRequest, UserCreate, UserUpdate,
    RegisterRequest, RegisterResponse, UpdateProfileRequest, ChangePasswordRequest,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ─── Login ────────────────────────────────────────────────────────────────────
@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.username == payload.username) | (User.email == payload.username),
        User.is_active == True,
    ).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
        )

    access_token = create_access_token(
    data={"sub": str(user.id)}  # <--- WAJIB: id harus di-string-kan
)
    refresh_token_str = create_refresh_token({"sub": user.id})

    # Persist refresh token
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    db_token = RefreshToken(
        user_id=user.id,
        token=refresh_token_str,
        expires_at=expires_at,
    )
    db.add(db_token)
    db.commit()

    # Fetch accessible plants
    if user.is_superuser:
        plants = db.query(Plant).filter(Plant.is_active == True).all()
    else:
        plant_ids = [up.plant_id for up in db.query(UserPlant).filter(UserPlant.user_id == user.id).all()]
        plants = db.query(Plant).filter(Plant.id.in_(plant_ids), Plant.is_active == True).all()

    return LoginResponse(
        token=Token(
            access_token=access_token,
            refresh_token=refresh_token_str,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
        user=UserResponse.model_validate(user),
        accessible_plants=[PlantBasic.model_validate(p) for p in plants],
    )


# ─── Refresh Token ────────────────────────────────────────────────────────────
@router.post("/refresh", response_model=Token)
def refresh_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    token_data = decode_token(payload.refresh_token)
    if token_data is None or token_data.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token tidak valid")

    db_token = db.query(RefreshToken).filter(
        RefreshToken.token == payload.refresh_token,
        RefreshToken.is_revoked == False,
    ).first()

    if not db_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token tidak ditemukan atau sudah dicabut")

    if db_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token sudah expired")

    # Revoke old, issue new
    db_token.is_revoked = True

    user_id = token_data.get("sub")
    new_access = create_access_token({"sub": user_id})
    new_refresh = create_refresh_token({"sub": user_id})

    new_db_token = RefreshToken(
        user_id=user_id,
        token=new_refresh,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_db_token)
    db.commit()

    return Token(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ─── Logout ───────────────────────────────────────────────────────────────────
@router.post("/logout")
def logout(
    payload: RefreshTokenRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    db_token = db.query(RefreshToken).filter(
        RefreshToken.token == payload.refresh_token,
        RefreshToken.user_id == current_user.id,
    ).first()
    if db_token:
        db_token.is_revoked = True
        db.commit()
    return {"message": "Logout berhasil"}


# ─── Current User ─────────────────────────────────────────────────────────────
@router.get("/me", response_model=UserResponse)
def get_me(current_user: CurrentUser, db: Session = Depends(get_db)):
    from app.models.public import UserPlant as _UP
    plant_ids = [up.plant_id for up in db.query(_UP).filter(_UP.user_id == current_user.id).all()]
    return {
        "id": current_user.id, "username": current_user.username,
        "email": current_user.email, "full_name": current_user.full_name,
        "role": {"id": current_user.role.id, "name": current_user.role.name},
        "is_active": current_user.is_active, "is_superuser": current_user.is_superuser,
        "created_at": current_user.created_at, "plant_ids": plant_ids,
    }


# ─── Accessible Plants for Current User ───────────────────────────────────────
@router.get("/me/plants", response_model=list[PlantBasic])
def get_my_plants(current_user: CurrentUser, db: Session = Depends(get_db)):
    if current_user.is_superuser:
        plants = db.query(Plant).filter(Plant.is_active == True).all()
    else:
        plant_ids = [up.plant_id for up in db.query(UserPlant).filter(UserPlant.user_id == current_user.id).all()]
        plants = db.query(Plant).filter(Plant.id.in_(plant_ids), Plant.is_active == True).all()
    return plants


# ─── Register ─────────────────────────────────────────────────────────────────
@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """
    Registrasi akun baru (self-service).
    Akun baru otomatis mendapat role 'viewer' dan belum memiliki akses plant.
    Admin perlu assign plant dan role yang sesuai setelahnya.
    """
    # Domain restriction
    if not payload.email.lower().endswith(f"@{settings.ALLOWED_EMAIL_DOMAIN}"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Registration is restricted to @{settings.ALLOWED_EMAIL_DOMAIN} email addresses only"
        )
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    from app.models.public import Role
    viewer_role = db.query(Role).filter(Role.name == "viewer").first()
    if not viewer_role:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Role configuration error, contact administrator")

    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name.strip(),
        hashed_password=get_password_hash(payload.password),
        role_id=viewer_role.id,
        is_superuser=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return RegisterResponse(
        message="Registration successful. Contact an administrator to get plant access.",
        user=UserResponse.model_validate(user),
    )


# ─── Update Profile (self) ────────────────────────────────────────────────────
@router.patch("/me", response_model=UserResponse)
def update_my_profile(
    payload: UpdateProfileRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Update nama lengkap dan/atau email milik sendiri."""
    if payload.email and payload.email != current_user.email:
        existing = db.query(User).filter(User.email == payload.email, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use by another account")

    user = db.query(User).filter(User.id == current_user.id).first()
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.email is not None:
        user.email = payload.email

    db.commit()
    db.refresh(user)
    return user


# ─── Change Password (self) ───────────────────────────────────────────────────
@router.post("/me/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Ganti password milik sendiri."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    user = db.query(User).filter(User.id == current_user.id).first()
    user.hashed_password = get_password_hash(payload.new_password)

    # Revoke semua refresh token lama (paksa login ulang di perangkat lain)
    db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.id,
        RefreshToken.is_revoked == False,
    ).update({"is_revoked": True})

    db.commit()
    return {"message": "Password updated. Other sessions have been signed out."}

# ─── Roles ────────────────────────────────────────────────────────────────────

from app.models.public import Role as RoleModel
from pydantic import BaseModel as _BM
from typing import Optional as _Opt

class _RoleOut(_BM):
    id: int
    name: str
    description: _Opt[str]
    model_config = {"from_attributes": True}

@router.get("/roles", response_model=list[_RoleOut])
def list_roles(db: Session = Depends(get_db)):
    """Return all active roles. No auth required — used by admin user-creation form."""
    return db.query(RoleModel).filter(RoleModel.is_active == True).order_by(RoleModel.id).all()


# ════════════════════════════════════════════════════════
# GOOGLE SSO
# ════════════════════════════════════════════════════════

import httpx as _httpx
from pydantic import BaseModel as _GoogleBM

GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_USERINFO_URL   = "https://www.googleapis.com/oauth2/v3/userinfo"
ALLOWED_DOMAIN        = settings.ALLOWED_EMAIL_DOMAIN
GOOGLE_CLIENT_ID      = settings.GOOGLE_CLIENT_ID


class GoogleAuthRequest(_GoogleBM):
    credential: str   # Google ID token from frontend


def _verify_google_token(credential: str) -> dict:
    """
    Verify Google ID token against Google's tokeninfo endpoint.
    Returns the decoded payload on success.
    Raises HTTPException on invalid token or domain mismatch.
    """
    try:
        resp = _httpx.get(GOOGLE_TOKEN_INFO_URL, params={"id_token": credential}, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to verify Google token")

    # Confirm audience matches our client ID
    if payload.get("aud") != GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=400, detail="Invalid Google token audience")

    # Confirm email is verified
    if payload.get("email_verified") not in (True, "true"):
        raise HTTPException(status_code=400, detail="Google account email is not verified")

    # Enforce domain restriction
    email: str = payload.get("email", "")
    if not email.lower().endswith(f"@{ALLOWED_DOMAIN}"):
        raise HTTPException(
            status_code=403,
            detail=f"Access restricted to @{ALLOWED_DOMAIN} accounts only"
        )

    return payload


def _build_login_response(user: "User", db: "Session") -> dict:
    """Build the same LoginResponse shape used by regular login."""
    from app.models.public import UserPlant as _UP2, Plant as _Plant2
    plant_ids = [up.plant_id for up in db.query(_UP2).filter(_UP2.user_id == user.id).all()]
    if user.is_superuser:
        accessible = db.query(_Plant2).filter(_Plant2.is_active == True).all()
    else:
        accessible = db.query(_Plant2).filter(_Plant2.id.in_(plant_ids), _Plant2.is_active == True).all()

    access_token   = create_access_token({"sub": str(user.id)})
    refresh_token_ = create_refresh_token({"sub": str(user.id)})

    db.add(RefreshToken(
        user_id=user.id,
        token=refresh_token_,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    db.commit()

    return {
        "token": {"access_token": access_token, "token_type": "bearer"},
        "user": {
            "id": user.id, "username": user.username, "email": user.email,
            "full_name": user.full_name,
            "role": {"id": user.role.id, "name": user.role.name},
            "is_active": user.is_active, "is_superuser": user.is_superuser,
            "created_at": user.created_at.isoformat(),
            "plant_ids": plant_ids,
        },
        "accessible_plants": [
            {"id": p.id, "name": p.name, "code": p.code,
             "schema_name": p.schema_name, "is_active": p.is_active}
            for p in accessible
        ],
    }


@router.post("/google")
def google_sso(payload: GoogleAuthRequest, db: Session = Depends(get_db)):
    """
    Authenticate via Google ID token.
    - Validates token against Google API.
    - Enforces @cpp.co.id domain.
    - Creates account automatically on first SSO login (viewer role, no plant access).
    - Returns same LoginResponse shape as regular login.
    """
    google_data = _verify_google_token(payload.credential)

    email: str      = google_data["email"].lower()
    full_name: str  = google_data.get("name") or email.split("@")[0]
    google_sub: str = google_data["sub"]   # stable Google user ID

    # Look up existing user by email
    user = db.query(User).filter(User.email == email).first()

    if user:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is deactivated. Contact administrator.")
    else:
        # Auto-create on first SSO login
        from app.models.public import Role as _Role
        viewer_role = db.query(_Role).filter(_Role.name == "viewer").first()
        if not viewer_role:
            raise HTTPException(status_code=500, detail="Role configuration error")

        # Derive a unique username from the email local part
        base_username = email.split("@")[0].replace(".", "_").replace("-", "_")
        username = base_username
        suffix = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}_{suffix}"
            suffix += 1

        user = User(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=get_password_hash(google_sub),  # unusable password — SSO only
            role_id=viewer_role.id,
            is_superuser=False,
        )
        db.add(user)
        db.flush()
        db.refresh(user)

    return _build_login_response(user, db)
