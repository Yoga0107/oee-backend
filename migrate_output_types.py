"""
migrate_output_types.py
───────────────────────
Migrasi: buat tabel master_output_types dan seed 5 default output type
di semua plant schema yang ada.

Jalankan sekali:
    python migrate_output_types.py
"""

import sys
from sqlalchemy import text, inspect
from app.db.database import engine as public_engine, get_plant_db
from app.models.plant_schema import PlantBase, MasterOutputType, DEFAULT_OUTPUT_TYPES
from app.models.public import Plant

def migrate_schema(schema_name: str) -> None:
    db = next(get_plant_db(schema_name))
    try:
        # Buat tabel jika belum ada
        inspector = inspect(db.bind)
        tables = inspector.get_table_names(schema=schema_name)
        if "master_output_types" not in tables:
            db.execute(text(f"SET search_path TO {schema_name}"))
            PlantBase.metadata.create_all(
                bind=db.bind,
                tables=[MasterOutputType.__table__],
            )
            print(f"  [CREATE] Tabel master_output_types dibuat di schema '{schema_name}'")
        else:
            print(f"  [SKIP]   Tabel master_output_types sudah ada di schema '{schema_name}'")

        # Seed default data jika kosong
        db.execute(text(f"SET search_path TO {schema_name}"))
        db.expire_all()
        existing = db.query(MasterOutputType).count()
        if existing == 0:
            for d in DEFAULT_OUTPUT_TYPES:
                db.add(MasterOutputType(**d))
            db.commit()
            print(f"  [SEED]   {len(DEFAULT_OUTPUT_TYPES)} default output type ditambahkan")
        else:
            print(f"  [SKIP]   Data sudah ada ({existing} records), seed dilewati")
    finally:
        db.close()


def main():
    from sqlalchemy.orm import Session
    with Session(public_engine) as pub_db:
        plants = pub_db.query(Plant).filter(Plant.is_active == True).all()

    if not plants:
        print("Tidak ada plant aktif ditemukan.")
        sys.exit(0)

    print(f"Migrasi master_output_types untuk {len(plants)} plant:\n")
    for plant in plants:
        print(f"Plant: {plant.name} (schema: {plant.schema_name})")
        try:
            migrate_schema(plant.schema_name)
        except Exception as e:
            print(f"  [ERROR]  {e}")
        print()

    print("Migrasi selesai.")


if __name__ == "__main__":
    main()
