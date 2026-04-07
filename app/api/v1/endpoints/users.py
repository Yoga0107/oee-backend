"""
users.py
Admin-only user management: list, create, update, deactivate.
Superuser access required for all endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.deps import SuperUser, CurrentUser
from app.core.security import get_password_hash
from app.models.public import User, UserPlant, Role, Plant, UserModulePermission
from app.schemas.auth import UserCreate, UserUpdate, UserResponse, ResetPasswordResponse
from pydantic import BaseModel
from typing import List

VALID_MODULES = {"dashboard", "oee", "users", "plants", "settings", "equipment", "scm-turnover"}


class ModulePermissionsPayload(BaseModel):
    modules: List[str]  # list of module names; empty list = use role defaults

TEMP_PASSWORD = "Qweqwe123"

router = APIRouter(prefix="/users", tags=["Users"])


def _build_response(user: User, db: Session) -> dict:
    """Build UserResponse dict with plant_ids populated."""
    plant_ids = [
        up.plant_id
        for up in db.query(UserPlant).filter(UserPlant.user_id == user.id).all()
    ]
    return {
        "id":                   user.id,
        "username":             user.username,
        "email":                user.email,
        "full_name":            user.full_name,
        "role":                 {"id": user.role.id, "name": user.role.name},
        "is_active":            user.is_active,
        "is_superuser":         user.is_superuser,
        "must_change_password": user.must_change_password,
        "created_at":           user.created_at,
        "plant_ids":            plant_ids,
    }


@router.get("/", response_model=list[UserResponse])
def list_users(admin: SuperUser, db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    return [_build_response(u, db) for u in users]


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, admin: SuperUser, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already in use")
    if not db.query(Role).filter(Role.id == payload.role_id).first():
        raise HTTPException(status_code=404, detail="Role not found")

    for pid in payload.plant_ids:
        if not db.query(Plant).filter(Plant.id == pid, Plant.is_active == True).first():
            raise HTTPException(status_code=404, detail=f"Plant id={pid} not found")

    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        # Admin-created users get a temporary password and must change it on first login
        hashed_password=get_password_hash(TEMP_PASSWORD),
        must_change_password=True,
        role_id=payload.role_id,
        created_by_id=admin.id,
    )
    db.add(user)
    db.flush()

    for plant_id in payload.plant_ids:
        db.add(UserPlant(user_id=user.id, plant_id=plant_id, created_by_id=admin.id))

    db.commit()
    db.refresh(user)
    return _build_response(user, db)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, payload: UserUpdate, admin: SuperUser, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent deactivating own account
    if payload.is_active is False and user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    if payload.role_id and not db.query(Role).filter(Role.id == payload.role_id).first():
        raise HTTPException(status_code=404, detail="Role not found")

    update_data = payload.model_dump(exclude_none=True, exclude={"plant_ids"})
    for k, v in update_data.items():
        setattr(user, k, v)

    if payload.plant_ids is not None:
        # Validate all plant_ids
        for pid in payload.plant_ids:
            if not db.query(Plant).filter(Plant.id == pid, Plant.is_active == True).first():
                raise HTTPException(status_code=404, detail=f"Plant id={pid} not found")
        db.query(UserPlant).filter(UserPlant.user_id == user_id).delete()
        for plant_id in payload.plant_ids:
            db.add(UserPlant(user_id=user_id, plant_id=plant_id, created_by_id=admin.id))

    db.commit()
    db.refresh(user)
    return _build_response(user, db)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(user_id: int, admin: SuperUser, db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.commit()


@router.post("/{user_id}/reset-password", response_model=ResetPasswordResponse)
def reset_password(user_id: int, admin: SuperUser, db: Session = Depends(get_db)):
    """
    Superuser resets a user's password to the system temporary password.
    The user will be forced to change it on next login.
    """
    if not admin.is_superuser:
        raise HTTPException(status_code=403, detail="Only superusers can reset passwords")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot reset your own password via this endpoint")

    user.hashed_password    = get_password_hash(TEMP_PASSWORD)
    user.must_change_password = True

    # Revoke all existing refresh tokens — force re-login
    from app.models.public import RefreshToken
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.is_revoked == False,
    ).update({"is_revoked": True})

    db.commit()
    return ResetPasswordResponse(
        message=f"Password untuk {user.username} berhasil direset.",
        temp_password=TEMP_PASSWORD,
    )


# ── Module Permissions ────────────────────────────────────────────────────────

@router.get("/me/modules", response_model=dict)
def get_my_modules(current_user: CurrentUser, db: Session = Depends(get_db)):
    """
    Get module permissions for the currently logged-in user.
    Accessible by any authenticated user (used on login/session restore).
    """
    perms = db.query(UserModulePermission).filter(
        UserModulePermission.user_id == current_user.id
    ).all()

    return {
        "user_id": current_user.id,
        "modules": [p.module for p in perms],
        "use_role_default": len(perms) == 0,
    }


@router.get("/{user_id}/modules", response_model=dict)
def get_user_modules(user_id: int, admin: SuperUser, db: Session = Depends(get_db)):
    """
    Get module permissions for a user.
    Returns {"modules": [...], "use_role_default": bool}
    If use_role_default is True, the user has no custom overrides.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    perms = db.query(UserModulePermission).filter(
        UserModulePermission.user_id == user_id
    ).all()

    return {
        "user_id": user_id,
        "modules": [p.module for p in perms],
        "use_role_default": len(perms) == 0,
    }


@router.put("/{user_id}/modules", response_model=dict)
def set_user_modules(
    user_id: int,
    payload: ModulePermissionsPayload,
    admin: SuperUser,
    db: Session = Depends(get_db),
):
    """
    Set module permissions for a user.
    - Pass a list of module names to grant explicit access.
    - Pass an empty list to remove all custom overrides (revert to role defaults).
    Valid modules: dashboard, oee, users, plants, settings
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate module names
    invalid = set(payload.modules) - VALID_MODULES
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Module tidak valid: {', '.join(invalid)}. Harus salah satu dari: {', '.join(sorted(VALID_MODULES))}",
        )

    # Delete existing permissions
    db.query(UserModulePermission).filter(
        UserModulePermission.user_id == user_id
    ).delete()

    # Insert new permissions
    for module in set(payload.modules):
        db.add(UserModulePermission(
            user_id=user_id,
            module=module,
            created_by_id=admin.id,
        ))

    db.commit()

    # Re-query to return current state
    perms = db.query(UserModulePermission).filter(
        UserModulePermission.user_id == user_id
    ).all()

    return {
        "user_id": user_id,
        "modules": [p.module for p in perms],
        "use_role_default": len(perms) == 0,
    }