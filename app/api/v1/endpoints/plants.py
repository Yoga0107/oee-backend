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


@router.get("/", response_model=list[PlantResponse])
def list_plants(current_user: CurrentUser, db: Session = Depends(get_db)):
    if current_user.is_superuser:
        return db.query(Plant).all()
    plant_ids = [up.plant_id for up in db.query(UserPlant).filter(UserPlant.user_id == current_user.id)]
    return db.query(Plant).filter(Plant.id.in_(plant_ids)).all()


@router.post("/", response_model=PlantResponse, status_code=status.HTTP_201_CREATED)
def create_plant(
    payload: PlantCreate,
    admin: SuperUser,
    db: Session = Depends(get_db),
):
    existing = db.query(Plant).filter(
        (Plant.code == payload.code) | (Plant.name == payload.name)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Plant dengan nama atau kode tersebut sudah ada")

    schema_name = _slugify_schema(payload.code)

    plant = Plant(
        name=payload.name,
        code=payload.code,
        schema_name=schema_name,
        description=payload.description,
        created_by_id=admin.id,
    )
    db.add(plant)
    db.commit()
    db.refresh(plant)

    # Provision the PostgreSQL schema + tables
    create_plant_schema(schema_name)
    init_plant_schema_tables(schema_name)

    return plant


@router.delete("/{plant_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_plant(plant_id: int, admin: SuperUser, db: Session = Depends(get_db)):
    plant = db.query(Plant).filter(Plant.id == plant_id).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant tidak ditemukan")
    plant.is_active = False
    db.commit()


@router.post("/{plant_id}/migrate-schema", status_code=200)
def migrate_plant_schema_endpoint(plant_id: int, admin: SuperUser, db: Session = Depends(get_db)):
    """
    Paksa jalankan migrasi schema untuk plant tertentu.
    Berguna jika tabel baru (machine_losses) belum ada di plant lama.
    """
    plant = db.query(Plant).filter(Plant.id == plant_id).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant tidak ditemukan")
    try:
        from app.db.migrate_plant_schema import migrate_plant_schema
        migrate_plant_schema(plant.schema_name)
        return {"message": f"Migrasi schema '{plant.schema_name}' berhasil"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Migrasi gagal: {str(e)}")
