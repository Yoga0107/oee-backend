"""
migrate_throughput_logs.py
--------------------------
Membuat tabel standard_throughput_logs di semua plant schema yang sudah ada.
Aman dijalankan berkali-kali (idempotent).

Usage:
    python migrate_throughput_logs.py
"""

from sqlalchemy import text
from app.db.database import engine, get_schema_engine
from app.models.public import Plant
from sqlalchemy.orm import Session


def get_all_plant_schemas() -> list[str]:
    with Session(engine) as db:
        plants = db.query(Plant).filter(Plant.is_active == True).all()
        return [p.schema_name for p in plants]


def migrate_throughput_logs(schema_name: str) -> None:
    s = schema_name
    schema_engine = get_schema_engine(s)

    with schema_engine.connect() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".standard_throughput_logs (
                id                      SERIAL PRIMARY KEY,
                standard_throughput_id  INTEGER NOT NULL
                                          REFERENCES "{s}".master_standard_throughputs(id) ON DELETE CASCADE,
                change_number           INTEGER NOT NULL,
                old_throughput          INTEGER,
                new_throughput          INTEGER NOT NULL,
                old_remarks             VARCHAR(500),
                new_remarks             VARCHAR(500),
                reason                  VARCHAR(1000),
                changed_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                changed_by_id           INTEGER
            )
        """))
        conn.execute(text(f"""
            ALTER TABLE "{s}".master_standard_throughputs
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE
        """))
        conn.commit()
        print(f"  ✅ standard_throughput_logs + is_active OK ({s})")


if __name__ == "__main__":
    print("🔄 Migrating standard_throughput_logs for all plant schemas...")
    schemas = get_all_plant_schemas()
    if not schemas:
        print("  ℹ️  Tidak ada plant yang terdaftar.")
    else:
        for schema in schemas:
            try:
                migrate_throughput_logs(schema)
            except Exception as e:
                print(f"  ❌ Error pada schema '{schema}': {e}")
    print("✅ Selesai.")
