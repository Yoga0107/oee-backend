from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import re

from app.db.database import get_db, create_plant_schema, init_plant_schema_tables
from app.core.deps import SuperUser, CurrentUser
from app.models.public import Plant, UserPlant
from app.schemas.master import PlantCreate, PlantResponse

router = APIRouter(prefix="/plants", tags=["Plants"])


def _slugify_schema(name: str) -> str:
    """Convert plant name to a valid PostgreSQL schema name."""
    slug = re.sub(r"[^a-z0-9]", "_", name.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return f"plant_{slug}"


def _require_admin(current_user: CurrentUser) -> CurrentUser:
    """Allow superuser OR administrator role to manage plants."""
    if current_user.is_superuser:
        return current_user
    if current_user.role and current_user.role.name == "administrator":
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Akses ditolak: hanya superuser atau administrator yang dapat mengelola plant",
    )


@router.get("/", response_model=list[PlantResponse])
def list_plants(current_user: CurrentUser, db: Session = Depends(get_db)):
    if current_user.is_superuser or (current_user.role and current_user.role.name == "administrator"):
        return db.query(Plant).all()
    plant_ids = [up.plant_id for up in db.query(UserPlant).filter(UserPlant.user_id == current_user.id)]
    return db.query(Plant).filter(Plant.id.in_(plant_ids)).all()


@router.post("/", response_model=PlantResponse, status_code=status.HTTP_201_CREATED)
def create_plant(
    payload: PlantCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    _require_admin(current_user)

    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nama plant tidak boleh kosong")
    if not payload.code.strip():
        raise HTTPException(status_code=400, detail="Kode plant tidak boleh kosong")

    existing = db.query(Plant).filter(
        (Plant.code == payload.code.upper()) | (Plant.name == payload.name)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Plant dengan nama atau kode tersebut sudah ada")

    schema_name = _slugify_schema(payload.code)

    # Guard: schema_name conflicts
    if db.query(Plant).filter(Plant.schema_name == schema_name).first():
        raise HTTPException(status_code=400, detail=f"Schema '{schema_name}' sudah digunakan oleh plant lain")

    plant = Plant(
        name=payload.name.strip(),
        code=payload.code.upper().strip(),
        schema_name=schema_name,
        description=payload.description,
        created_by_id=current_user.id,
    )
    db.add(plant)
    db.commit()
    db.refresh(plant)

    # Provision the PostgreSQL schema + tables
    try:
        create_plant_schema(schema_name)
        init_plant_schema_tables(schema_name)
    except Exception as e:
        # Rollback plant record if schema creation fails
        db.delete(plant)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Gagal membuat schema database: {str(e)}")

    return plant


@router.patch("/{plant_id}", response_model=PlantResponse)
def update_plant(
    plant_id: int,
    payload: PlantCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    plant = db.query(Plant).filter(Plant.id == plant_id).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant tidak ditemukan")

    # Check name/code uniqueness excluding self
    conflict = db.query(Plant).filter(
        Plant.id != plant_id,
        (Plant.name == payload.name) | (Plant.code == payload.code.upper()),
    ).first()
    if conflict:
        raise HTTPException(status_code=400, detail="Nama atau kode sudah digunakan plant lain")

    plant.name        = payload.name.strip()
    plant.code        = payload.code.upper().strip()
    plant.description = payload.description
    db.commit()
    db.refresh(plant)
    return plant


@router.patch("/{plant_id}/toggle-active", response_model=PlantResponse)
def toggle_plant_active(
    plant_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    plant = db.query(Plant).filter(Plant.id == plant_id).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant tidak ditemukan")
    plant.is_active = not plant.is_active
    db.commit()
    db.refresh(plant)
    return plant


@router.delete("/{plant_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_plant(plant_id: int, admin: SuperUser, db: Session = Depends(get_db)):
    plant = db.query(Plant).filter(Plant.id == plant_id).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant tidak ditemukan")
    plant.is_active = False
    db.commit()


@router.post("/{plant_id}/migrate-schema", status_code=200)
def migrate_plant_schema_endpoint(plant_id: int, current_user: CurrentUser, db: Session = Depends(get_db)):
    _require_admin(current_user)
    plant = db.query(Plant).filter(Plant.id == plant_id).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant tidak ditemukan")
    try:
        from app.db.migrate_plant_schema import migrate_plant_schema
        migrate_plant_schema(plant.schema_name)
        return {"message": f"Migrasi schema '{plant.schema_name}' berhasil"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Migrasi gagal: {str(e)}")
