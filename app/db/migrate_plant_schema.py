"""
migrate_plant_schema.py
-----------------------
Menangani perubahan skema untuk plant yang sudah ada.
Jalankan sekali setelah update model:

    python -m app.db.migrate_plant_schema

Atau dipanggil otomatis dari lifespan di main.py.
"""

from sqlalchemy import text, inspect
from app.db.database import engine, get_schema_engine
from app.models.public import Plant
from sqlalchemy.orm import Session


def get_all_plant_schemas() -> list[str]:
    """Ambil semua schema_name dari tabel plants."""
    with Session(engine) as db:
        plants = db.query(Plant).filter(Plant.is_active == True).all()
        return [p.schema_name for p in plants]


def migrate_plant_schema(schema_name: str) -> None:
    """
    Migrasi satu plant schema:
    1. Buat tabel machine_losses jika belum ada
    2. Migrasi data dari loss_level_1/2/3 jika ada
    3. Drop tabel lama (opsional, dikomentari untuk keamanan)
    """
    schema_engine = get_schema_engine(schema_name)

    with schema_engine.connect() as conn:
        # ── 1. Buat tabel machine_losses jika belum ada ─────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{schema_name}".machine_losses (
                id           SERIAL PRIMARY KEY,
                parent_id    INTEGER REFERENCES "{schema_name}".machine_losses(id) ON DELETE RESTRICT,
                level        SMALLINT NOT NULL CHECK (level IN (1, 2, 3)),
                name         VARCHAR(200) NOT NULL,
                description  TEXT,
                sort_order   INTEGER DEFAULT 0,
                is_active    BOOLEAN DEFAULT TRUE,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id INTEGER,
                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id INTEGER
            )
        """))
        conn.commit()

        # ── 2. Cek apakah ada data lama di loss_level_1/2/3 ─────────────────
        # Cek apakah tabel lama masih ada
        old_tables_exist = conn.execute(text(f"""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = '{schema_name}'
            AND table_name IN ('loss_level_1', 'loss_level_2', 'loss_level_3')
        """)).scalar()

        if old_tables_exist > 0:
            # Cek apakah machine_losses sudah punya data (jangan migrate dua kali)
            existing_count = conn.execute(text(f"""
                SELECT COUNT(*) FROM "{schema_name}".machine_losses
            """)).scalar()

            if existing_count == 0:
                # Migrasi level 1
                conn.execute(text(f"""
                    INSERT INTO "{schema_name}".machine_losses
                        (id, parent_id, level, name, description, sort_order, is_active, created_at, created_by_id)
                    SELECT id, NULL, 1, name, description, id, TRUE, created_at, created_by_id
                    FROM "{schema_name}".loss_level_1
                    ON CONFLICT (id) DO NOTHING
                """))

                # Migrasi level 2
                conn.execute(text(f"""
                    INSERT INTO "{schema_name}".machine_losses
                        (id, parent_id, level, name, description, sort_order, is_active, created_at, created_by_id)
                    SELECT id, level_1_id, 2, name, description, id, TRUE, created_at, created_by_id
                    FROM "{schema_name}".loss_level_2
                    ON CONFLICT (id) DO NOTHING
                """))

                # Migrasi level 3 — id harus unik, offset agar tidak bentrok dengan L1/L2
                # Ambil max id dulu
                max_id = conn.execute(text(f"""
                    SELECT COALESCE(MAX(id), 0) FROM "{schema_name}".machine_losses
                """)).scalar()

                conn.execute(text(f"""
                    INSERT INTO "{schema_name}".machine_losses
                        (parent_id, level, name, description, sort_order, is_active, created_at, created_by_id)
                    SELECT level_2_id, 3, name, description, id, TRUE, created_at, created_by_id
                    FROM "{schema_name}".loss_level_3
                """))

                conn.commit()
                print(f"  ✅ Migrasi data loss level dari tabel lama ke machine_losses ({schema_name})")
            else:
                print(f"  ⏭  machine_losses sudah punya data, skip migrasi ({schema_name})")

            # Reset sequence agar tidak bentrok
            conn.execute(text(f"""
                SELECT setval(
                    pg_get_serial_sequence('"{schema_name}".machine_losses', 'id'),
                    COALESCE((SELECT MAX(id) FROM "{schema_name}".machine_losses), 1)
                )
            """))
            conn.commit()

        # ── 3. Pastikan kolom is_active ada di shift, feed_code, line ────────
        for tbl in ["master_shifts", "master_feed_codes", "master_lines"]:
            try:
                conn.execute(text(f"""
                    ALTER TABLE "{schema_name}".{tbl}
                    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE
                """))
                conn.commit()
            except Exception:
                conn.rollback()

        print(f"  ✅ Schema {schema_name} OK")


def run_all_migrations():
    """Migrasi semua plant schema yang terdaftar."""
    print("🔄 Menjalankan migrasi plant schema...")
    schemas = get_all_plant_schemas()
    if not schemas:
        print("  ℹ️  Tidak ada plant terdaftar.")
        return
    for schema in schemas:
        try:
            migrate_plant_schema(schema)
        except Exception as e:
            print(f"  ❌ Error migrasi {schema}: {e}")
    print("✅ Selesai migrasi semua plant schema.")


if __name__ == "__main__":
    run_all_migrations()
"""
migrate_plant_schema.py
-----------------------
Menangani perubahan skema untuk plant yang sudah ada.
Jalankan sekali setelah update model:

    python -m app.db.migrate_plant_schema

Atau dipanggil otomatis dari lifespan di main.py.
"""

from sqlalchemy import text, inspect
from app.db.database import engine, get_schema_engine
from app.models.public import Plant
from sqlalchemy.orm import Session


def get_all_plant_schemas() -> list[str]:
    """Ambil semua schema_name dari tabel plants."""
    with Session(engine) as db:
        plants = db.query(Plant).filter(Plant.is_active == True).all()
        return [p.schema_name for p in plants]


def migrate_plant_schema(schema_name: str) -> None:
    """
    Migrasi satu plant schema:
    1. Buat tabel machine_losses jika belum ada
    2. Migrasi data dari loss_level_1/2/3 jika ada
    3. Drop tabel lama (opsional, dikomentari untuk keamanan)
    """
    schema_engine = get_schema_engine(schema_name)

    with schema_engine.connect() as conn:
        # ── 1. Buat tabel machine_losses jika belum ada ─────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{schema_name}".machine_losses (
                id           SERIAL PRIMARY KEY,
                parent_id    INTEGER REFERENCES "{schema_name}".machine_losses(id) ON DELETE RESTRICT,
                level        SMALLINT NOT NULL CHECK (level IN (1, 2, 3)),
                name         VARCHAR(200) NOT NULL,
                description  TEXT,
                sort_order   INTEGER DEFAULT 0,
                is_active    BOOLEAN DEFAULT TRUE,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id INTEGER,
                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id INTEGER
            )
        """))
        conn.commit()

        # ── 2. Cek apakah ada data lama di loss_level_1/2/3 ─────────────────
        # Cek apakah tabel lama masih ada
        old_tables_exist = conn.execute(text(f"""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = '{schema_name}'
            AND table_name IN ('loss_level_1', 'loss_level_2', 'loss_level_3')
        """)).scalar()

        if old_tables_exist > 0:
            # Cek apakah machine_losses sudah punya data (jangan migrate dua kali)
            existing_count = conn.execute(text(f"""
                SELECT COUNT(*) FROM "{schema_name}".machine_losses
            """)).scalar()

            if existing_count == 0:
                # Migrasi level 1
                conn.execute(text(f"""
                    INSERT INTO "{schema_name}".machine_losses
                        (id, parent_id, level, name, description, sort_order, is_active, created_at, created_by_id)
                    SELECT id, NULL, 1, name, description, id, TRUE, created_at, created_by_id
                    FROM "{schema_name}".loss_level_1
                    ON CONFLICT (id) DO NOTHING
                """))

                # Migrasi level 2
                conn.execute(text(f"""
                    INSERT INTO "{schema_name}".machine_losses
                        (id, parent_id, level, name, description, sort_order, is_active, created_at, created_by_id)
                    SELECT id, level_1_id, 2, name, description, id, TRUE, created_at, created_by_id
                    FROM "{schema_name}".loss_level_2
                    ON CONFLICT (id) DO NOTHING
                """))

                # Migrasi level 3 — id harus unik, offset agar tidak bentrok dengan L1/L2
                # Ambil max id dulu
                max_id = conn.execute(text(f"""
                    SELECT COALESCE(MAX(id), 0) FROM "{schema_name}".machine_losses
                """)).scalar()

                conn.execute(text(f"""
                    INSERT INTO "{schema_name}".machine_losses
                        (parent_id, level, name, description, sort_order, is_active, created_at, created_by_id)
                    SELECT level_2_id, 3, name, description, id, TRUE, created_at, created_by_id
                    FROM "{schema_name}".loss_level_3
                """))

                conn.commit()
                print(f"  ✅ Migrasi data loss level dari tabel lama ke machine_losses ({schema_name})")
            else:
                print(f"  ⏭  machine_losses sudah punya data, skip migrasi ({schema_name})")

            # Reset sequence agar tidak bentrok
            conn.execute(text(f"""
                SELECT setval(
                    pg_get_serial_sequence('"{schema_name}".machine_losses', 'id'),
                    COALESCE((SELECT MAX(id) FROM "{schema_name}".machine_losses), 1)
                )
            """))
            conn.commit()

        # ── 3. Pastikan kolom is_active ada di shift, feed_code, line ────────
        for tbl in ["master_shifts", "master_feed_codes", "master_lines"]:
            try:
                conn.execute(text(f"""
                    ALTER TABLE "{schema_name}".{tbl}
                    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE
                """))
                conn.commit()
            except Exception:
                conn.rollback()

        print(f"  ✅ Schema {schema_name} OK")


def run_all_migrations():
    """Migrasi semua plant schema yang terdaftar."""
    print("🔄 Menjalankan migrasi plant schema...")
    schemas = get_all_plant_schemas()
    if not schemas:
        print("  ℹ️  Tidak ada plant terdaftar.")
        return
    for schema in schemas:
        try:
            migrate_plant_schema(schema)
        except Exception as e:
            print(f"  ❌ Error migrasi {schema}: {e}")
    print("✅ Selesai migrasi semua plant schema.")


if __name__ == "__main__":
    run_all_migrations()
