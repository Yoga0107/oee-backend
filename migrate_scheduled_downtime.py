"""
migrate_line_jalan_inputs.py
────────────────────────────
Migrasi:
1. Tambah kolom is_scheduled_downtime ke master_machine_losses
2. Buat tabel line_jalan_inputs

Jalankan sekali:
    python migrate_line_jalan_inputs.py
"""

import sys
from sqlalchemy import (
    text,
    inspect,
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import Session

from app.db.database import engine as public_engine, get_plant_db
from app.models.public import Plant
from app.models.plant_schema import PlantBase


def migrate_schema(schema_name: str) -> None:
    db = next(get_plant_db(schema_name))

    try:
        inspector = inspect(db.bind)

        # =========================================================
        # 1. ADD COLUMN is_scheduled_downtime
        # =========================================================

        columns = [
            col["name"]
            for col in inspector.get_columns(
                "master_machine_losses",
                schema=schema_name,
            )
        ]

        if "is_scheduled_downtime" not in columns:
            db.execute(
                text(f"""
                    ALTER TABLE {schema_name}.master_machine_losses
                    ADD COLUMN is_scheduled_downtime BOOLEAN NOT NULL DEFAULT FALSE
                """)
            )

            db.commit()

            print(
                f"  [ALTER] Kolom is_scheduled_downtime ditambahkan "
                f"ke {schema_name}.master_machine_losses"
            )
        else:
            print(
                f"  [SKIP]  Kolom is_scheduled_downtime sudah ada "
                f"di {schema_name}.master_machine_losses"
            )

        # =========================================================
        # 2. CREATE TABLE line_jalan_inputs
        # =========================================================

        tables = inspector.get_table_names(schema=schema_name)

        if "line_jalan_inputs" not in tables:

            from sqlalchemy import Table

            line_jalan_inputs = Table(
                "line_jalan_inputs",
                PlantBase.metadata,

                Column(
                    "id",
                    Integer,
                    primary_key=True,
                    autoincrement=True,
                ),

                Column(
                    "date",
                    DateTime,
                    nullable=False,
                ),

                Column(
                    "line_id",
                    Integer,
                    ForeignKey(
                        f"{schema_name}.master_lines.id",
                        ondelete="RESTRICT",
                    ),
                    nullable=False,
                ),

                Column(
                    "shift_id",
                    Integer,
                    ForeignKey(
                        f"{schema_name}.master_shifts.id",
                        ondelete="RESTRICT",
                    ),
                    nullable=False,
                ),

                Column(
                    "feed_code_id",
                    Integer,
                    ForeignKey(
                        f"{schema_name}.master_feed_codes.id",
                        ondelete="RESTRICT",
                    ),
                    nullable=False,
                ),

                Column(
                    "time_from",
                    String(8),
                    nullable=False,
                ),

                Column(
                    "time_to",
                    String(8),
                    nullable=False,
                ),

                Column(
                    "duration_minutes",
                    Float,
                    nullable=False,
                ),

                Column(
                    "remarks",
                    String(500),
                    nullable=True,
                ),

                Column(
                    "is_active",
                    Boolean,
                    nullable=False,
                    server_default=text("TRUE"),
                ),

                Column(
                    "created_at",
                    DateTime,
                    server_default=text("NOW()"),
                ),

                Column(
                    "created_by_id",
                    Integer,
                    nullable=True,
                ),

                Column(
                    "updated_at",
                    DateTime,
                    server_default=text("NOW()"),
                ),

                Column(
                    "updated_by_id",
                    Integer,
                    nullable=True,
                ),

                schema=schema_name,
            )

            db.execute(text(f"SET search_path TO {schema_name}"))

            PlantBase.metadata.create_all(
                bind=db.bind,
                tables=[line_jalan_inputs],
            )

            # =====================================================
            # CREATE INDEX
            # =====================================================

            index_name = f"ix_{schema_name}_line_jalan_date_line_shift"

            db.execute(
                text(f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON {schema_name}.line_jalan_inputs
                    (date, line_id, shift_id)
                """)
            )

            db.commit()

            print(
                f"  [CREATE] Tabel line_jalan_inputs dibuat "
                f"di schema '{schema_name}'"
            )

        else:
            print(
                f"  [SKIP]  Tabel line_jalan_inputs sudah ada "
                f"di schema '{schema_name}'"
            )

    finally:
        db.close()


def main():

    with Session(public_engine) as pub_db:
        plants = (
            pub_db.query(Plant)
            .filter(Plant.is_active == True)
            .all()
        )

    if not plants:
        print("Tidak ada plant aktif ditemukan.")
        sys.exit(0)

    print(f"Migrasi line_jalan_inputs untuk {len(plants)} plant:\n")

    for plant in plants:

        print(
            f"Plant: {plant.name} "
            f"(schema: {plant.schema_name})"
        )

        try:
            migrate_schema(plant.schema_name)

        except Exception as e:
            print(f"  [ERROR] {e}")

        print()

    print("Migrasi selesai.")


if __name__ == "__main__":
    main()