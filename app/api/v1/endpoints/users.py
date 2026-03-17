from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.deps import SuperUser, CurrentUser
from app.core.security import get_password_hash
from app.models.public import User, UserPlant, Role
from app.schemas.auth import UserCreate, UserUpdate, UserResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/", response_model=list[UserResponse])
def list_users(admin: SuperUser, db: Session = Depends(get_db)):
    return db.query(User).all()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, admin: SuperUser, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email sudah digunakan")
    if not db.query(Role).filter(Role.id == payload.role_id).first():
        raise HTTPException(status_code=404, detail="Role tidak ditemukan")

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
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, payload: UserUpdate, admin: SuperUser, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")

    update_data = payload.model_dump(exclude_none=True, exclude={"plant_ids"})
    for k, v in update_data.items():
        setattr(user, k, v)

    if payload.plant_ids is not None:
        db.query(UserPlant).filter(UserPlant.user_id == user_id).delete()
        for plant_id in payload.plant_ids:
            db.add(UserPlant(user_id=user_id, plant_id=plant_id, created_by_id=admin.id))

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(user_id: int, admin: SuperUser, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    user.is_active = False
    db.commit()
