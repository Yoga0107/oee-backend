from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional, Annotated

from app.db.database import get_db, get_plant_db
from app.core.security import decode_token
from app.models.public import User, Plant, UserPlant

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    print(payload)

    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tidak valid atau sudah expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # PERBAIKAN: Pastikan dikonversi ke integer
    try:
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            raise ValueError("No sub in payload")
        user_id = int(user_id_raw) 
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Format token tidak valid (sub missing/invalid)",
        )

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User tidak ditemukan atau tidak aktif",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak: hanya administrator yang dapat melakukan ini",
        )
    return current_user


SuperUser = Annotated[User, Depends(require_superuser)]


def get_plant_from_header(
    x_plant_id: Optional[int] = Header(default=None, alias="X-Plant-ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Plant:
    """
    Validate that the requesting user has access to the plant specified in X-Plant-ID header.
    Superusers bypass the plant-membership check.
    """
    if x_plant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Header X-Plant-ID wajib disertakan",
        )

    plant = db.query(Plant).filter(Plant.id == x_plant_id, Plant.is_active == True).first()
    if not plant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plant dengan id {x_plant_id} tidak ditemukan",
        )

    if not current_user.is_superuser:
        access = (
            db.query(UserPlant)
            .filter(UserPlant.user_id == current_user.id, UserPlant.plant_id == x_plant_id)
            .first()
        )
        if not access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Anda tidak memiliki akses ke plant ini",
            )

    return plant


CurrentPlant = Annotated[Plant, Depends(get_plant_from_header)]
