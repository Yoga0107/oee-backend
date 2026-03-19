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
from app.models.public import User, UserPlant, Role, Plant
from app.schemas.auth import UserCreate, UserUpdate, UserResponse

router = APIRouter(prefix="/users", tags=["Users"])


def _build_response(user: User, db: Session) -> dict:
    """Build UserResponse dict with plant_ids populated."""
    plant_ids = [
        up.plant_id
        for up in db.query(UserPlant).filter(UserPlant.user_id == user.id).all()
    ]
    return {
        "id":           user.id,
        "username":     user.username,
        "email":        user.email,
        "full_name":    user.full_name,
        "role":         {"id": user.role.id, "name": user.role.name},
        "is_active":    user.is_active,
        "is_superuser": user.is_superuser,
        "created_at":   user.created_at,
        "plant_ids":    plant_ids,
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

    # Validate plant_ids
    for pid in payload.plant_ids:
        if not db.query(Plant).filter(Plant.id == pid, Plant.is_active == True).first():
            raise HTTPException(status_code=404, detail=f"Plant id={pid} not found")

    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
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
