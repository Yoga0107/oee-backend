"""
migrate_int_line.py
Run once to add `type` column to master_lines and create int_line_merge table
on every plant schema.

Usage:
    python migrate_int_line.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import engine
from app.db.database import get_plant_db
from sqlalchemy import text


def migrate_public():
    """Ambil daftar semua plant dari tabel public.plants."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, name, schema_name FROM public.plants WHERE is_active = true"))
        return result.fetchall()


def migrate_plant_schema(schema_name: str):
    print(f"  🔄  Migrating schema: {schema_name} ...")
    db = next(get_plant_db(schema_name))
    try:
        with db.bind.connect() as conn:
            # 1. Tambah kolom `type` ke master_lines (jika belum ada)
            conn.execute(text(f"""
                ALTER TABLE {schema_name}.master_lines
                ADD COLUMN IF NOT EXISTS type VARCHAR(20) NOT NULL DEFAULT 'physical';
            """))

            # 2. Buat tabel int_line_merge (jika belum ada)
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {schema_name}.int_line_merge (
                    parent_line_id INTEGER NOT NULL
                        REFERENCES {schema_name}.master_lines(id) ON DELETE CASCADE,
                    child_line_id  INTEGER NOT NULL
                        REFERENCES {schema_name}.master_lines(id) ON DELETE CASCADE,
                    PRIMARY KEY (parent_line_id, child_line_id),
                    CONSTRAINT uq_line_merge_parent_child_{schema_name}
                        UNIQUE (parent_line_id, child_line_id)
                );
            """))

            # 3. Index untuk mempercepat lookup child → parent
            conn.execute(text(f"""
                CREATE INDEX IF NOT EXISTS idx_int_line_merge_child_{schema_name}
                ON {schema_name}.int_line_merge (child_line_id);
            """))

            conn.commit()
        print(f"  ✅  Schema {schema_name} migrated successfully.")
    except Exception as e:
        print(f"  ❌  Error on schema {schema_name}: {e}")
    finally:
        db.close()


def migrate():
    print("🔄  Running migration: int_line_merge + master_lines.type ...")
    print()

    plants = migrate_public()
    if not plants:
        print("⚠️   Tidak ada plant aktif ditemukan di public.plants.")
        return

    print(f"📋  Ditemukan {len(plants)} plant:")
    for p in plants:
        print(f"     - [{p.id}] {p.name}  →  schema: {p.schema_name}")
    print()

    for p in plants:
        migrate_plant_schema(p.schema_name)

    print()
    print("🎉  Migration selesai untuk semua plant schema.")


if __name__ == "__main__":
    migrate()