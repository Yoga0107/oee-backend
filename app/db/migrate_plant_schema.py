"""
migrate_plant_schema.py
-----------------------
Satu-satunya sumber kebenaran untuk skema tabel plant.
Aman dijalankan berulang kali (idempotent — semua pakai IF NOT EXISTS).

Struktur master_machine_losses sesuai ERD:
  - master_machine_losses_lvl_1 : FLAT (machine_losses_lvl_1_id, name)
  - master_machine_losses_lvl_2 : FLAT (machine_losses_lvl_2_id, name)
  - master_machine_losses_lvl_3 : FLAT (machine_losses_lvl_3_id, name)
  - master_machine_losses       : hierarki ada di sini
                                  (machine_losses_id, machine_losses_lvl_1_id FK,
                                   machine_losses_lvl_2_id FK, machine_losses_lvl_3_id FK)

Usage:
    python -m app.db.migrate_plant_schema

Atau dipanggil otomatis dari:
    - main.py lifespan (startup)
    - plants endpoint saat create plant baru
"""

from sqlalchemy import text
from app.db.database import engine, get_schema_engine
from app.models.public import Plant
from sqlalchemy.orm import Session


def get_all_plant_schemas() -> list[str]:
    with Session(engine) as db:
        plants = db.query(Plant).filter(Plant.is_active == True).all()
        return [p.schema_name for p in plants]


def migrate_plant_schema(schema_name: str) -> None:
    schema_engine = get_schema_engine(schema_name)
    s = schema_name

    with schema_engine.connect() as conn:

        # ── 1. master_machine_losses_lvl_1 (FLAT — hanya id & name) ─────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".master_machine_losses_lvl_1 (
                machine_losses_lvl_1_id SERIAL PRIMARY KEY,
                name                    VARCHAR(200) NOT NULL
            )
        """))
        conn.commit()
        print(f"  ✅ master_machine_losses_lvl_1 OK ({s})")

        # ── 2. master_machine_losses_lvl_2 (FLAT — hanya id & name) ─────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".master_machine_losses_lvl_2 (
                machine_losses_lvl_2_id SERIAL PRIMARY KEY,
                name                    VARCHAR(200) NOT NULL
            )
        """))
        conn.commit()
        print(f"  ✅ master_machine_losses_lvl_2 OK ({s})")

        # ── 3. master_machine_losses_lvl_3 (FLAT — hanya id & name) ─────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".master_machine_losses_lvl_3 (
                machine_losses_lvl_3_id SERIAL PRIMARY KEY,
                name                    VARCHAR(200) NOT NULL
            )
        """))
        conn.commit()
        print(f"  ✅ master_machine_losses_lvl_3 OK ({s})")

        # ── 4. master_machine_losses (hierarki ada di sini) ──────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".master_machine_losses (
                machine_losses_id       SERIAL PRIMARY KEY,
                machine_losses_lvl_1_id INTEGER NOT NULL
                                          REFERENCES "{s}".master_machine_losses_lvl_1(machine_losses_lvl_1_id)
                                          ON DELETE RESTRICT,
                machine_losses_lvl_2_id INTEGER
                                          REFERENCES "{s}".master_machine_losses_lvl_2(machine_losses_lvl_2_id)
                                          ON DELETE RESTRICT,
                machine_losses_lvl_3_id INTEGER
                                          REFERENCES "{s}".master_machine_losses_lvl_3(machine_losses_lvl_3_id)
                                          ON DELETE RESTRICT,
                remarks                 TEXT,
                is_active               BOOLEAN DEFAULT TRUE,
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id           INTEGER,
                updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id           INTEGER
            )
        """))
        conn.commit()
        print(f"  ✅ master_machine_losses OK ({s})")

        # ── 5. master_shifts ─────────────────────────────────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".master_shifts (
                id            SERIAL PRIMARY KEY,
                name          VARCHAR(50) NOT NULL,
                time_from     TIME NOT NULL,
                time_to       TIME NOT NULL,
                remarks       VARCHAR(500),
                is_active     BOOLEAN DEFAULT TRUE,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id INTEGER,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id INTEGER
            )
        """))
        conn.commit()
        for col, coldef in [
            ("remarks",       "VARCHAR(500)"),
            ("is_active",     "BOOLEAN DEFAULT TRUE"),
            ("updated_at",    "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_by_id", "INTEGER"),
            ("created_by_id", "INTEGER"),
        ]:
            try:
                conn.execute(text(f'ALTER TABLE "{s}".master_shifts ADD COLUMN IF NOT EXISTS {col} {coldef}'))
                conn.commit()
            except Exception:
                conn.rollback()
        print(f"  ✅ master_shifts OK ({s})")

        # ── 6. master_feed_codes ─────────────────────────────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".master_feed_codes (
                id            SERIAL PRIMARY KEY,
                code          VARCHAR(50) UNIQUE NOT NULL,
                remarks       VARCHAR(500),
                is_active     BOOLEAN DEFAULT TRUE,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id INTEGER,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id INTEGER
            )
        """))
        conn.commit()
        for col, coldef in [
            ("remarks",       "VARCHAR(500)"),
            ("is_active",     "BOOLEAN DEFAULT TRUE"),
            ("updated_at",    "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_by_id", "INTEGER"),
            ("created_by_id", "INTEGER"),
        ]:
            try:
                conn.execute(text(f'ALTER TABLE "{s}".master_feed_codes ADD COLUMN IF NOT EXISTS {col} {coldef}'))
                conn.commit()
            except Exception:
                conn.rollback()
        print(f"  ✅ master_feed_codes OK ({s})")

        # ── 7. master_lines ──────────────────────────────────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".master_lines (
                id            SERIAL PRIMARY KEY,
                plant_id      INTEGER NOT NULL,
                name          VARCHAR(100) NOT NULL,
                code          VARCHAR(50),
                remarks       VARCHAR(500),
                is_active     BOOLEAN DEFAULT TRUE,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id INTEGER,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id INTEGER
            )
        """))
        conn.commit()
        for col, coldef in [
            ("plant_id",             "INTEGER NOT NULL DEFAULT 0"),
            ("code",                 "VARCHAR(50)"),
            ("remarks",              "VARCHAR(500)"),
            ("current_feed_code_id", "INTEGER"),
            ("is_active",            "BOOLEAN DEFAULT TRUE"),
            ("updated_at",           "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_by_id",        "INTEGER"),
            ("created_by_id",        "INTEGER"),
        ]:
            try:
                conn.execute(text(f'ALTER TABLE "{s}".master_lines ADD COLUMN IF NOT EXISTS {col} {coldef}'))
                conn.commit()
            except Exception:
                conn.rollback()
        try:
            conn.execute(text(f"""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                         WHERE constraint_schema = '{s}'
                           AND table_name = 'master_lines'
                           AND constraint_name = 'fk_master_lines_feed_code'
                    ) THEN
                        ALTER TABLE "{s}".master_lines
                            ADD CONSTRAINT fk_master_lines_feed_code
                            FOREIGN KEY (current_feed_code_id)
                            REFERENCES "{s}".master_feed_codes(id)
                            ON DELETE SET NULL;
                    END IF;
                END $$;
            """))
            conn.commit()
        except Exception:
            conn.rollback()
        print(f"  ✅ master_lines OK ({s})")

        # ── 8. master_standard_throughputs ───────────────────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".master_standard_throughputs (
                id                   SERIAL PRIMARY KEY,
                line_id              INTEGER NOT NULL
                                       REFERENCES "{s}".master_lines(id) ON DELETE RESTRICT,
                feed_code_id         INTEGER NOT NULL
                                       REFERENCES "{s}".master_feed_codes(id) ON DELETE RESTRICT,
                standard_throughput  INTEGER NOT NULL,
                remarks              VARCHAR(500),
                created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id        INTEGER,
                updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id        INTEGER,
                CONSTRAINT uq_line_feedcode UNIQUE (line_id, feed_code_id)
            )
        """))
        conn.commit()
        for col, coldef in [
            ("remarks",       "VARCHAR(500)"),
            ("updated_at",    "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_by_id", "INTEGER"),
            ("created_by_id", "INTEGER"),
        ]:
            try:
                conn.execute(text(f'ALTER TABLE "{s}".master_standard_throughputs ADD COLUMN IF NOT EXISTS {col} {coldef}'))
                conn.commit()
            except Exception:
                conn.rollback()
        print(f"  ✅ master_standard_throughputs OK ({s})")

        # ── 8b. standard_throughput_logs ─────────────────────────────────────
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
        print(f"  ✅ standard_throughput_logs OK ({s})")


        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".production_outputs (
                id               SERIAL PRIMARY KEY,
                group_id         VARCHAR(36) NOT NULL,
                date             TIMESTAMP NOT NULL,
                line_id          INTEGER NOT NULL
                                   REFERENCES "{s}".master_lines(id)  ON DELETE RESTRICT,
                shift_id         INTEGER NOT NULL
                                   REFERENCES "{s}".master_shifts(id) ON DELETE RESTRICT,
                feed_code_id     INTEGER
                                   REFERENCES "{s}".master_feed_codes(id) ON DELETE SET NULL,
                production_plan  INTEGER,
                output_type      VARCHAR(50) NOT NULL,
                category         VARCHAR(50) NOT NULL,
                quantity         INTEGER NOT NULL DEFAULT 0,
                remarks          VARCHAR(500),
                is_active        BOOLEAN DEFAULT TRUE,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id    INTEGER,
                updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id    INTEGER
            )
        """))
        conn.commit()
        for idx_name, idx_col in [
            (f"idx_{s}_po_group_id", "group_id"),
            (f"idx_{s}_po_date",     "date"),
            (f"idx_{s}_po_type",     "output_type"),
            (f"idx_{s}_po_category", "category"),
        ]:
            try:
                conn.execute(text(
                    f'CREATE INDEX IF NOT EXISTS {idx_name} '
                    f'ON "{s}".production_outputs ({idx_col})'
                ))
                conn.commit()
            except Exception:
                conn.rollback()
        for col, coldef in [
            ("group_id",      "VARCHAR(36)"),
            ("output_type",   "VARCHAR(50)"),
            ("category",      "VARCHAR(50)"),
            ("quantity",      "INTEGER NOT NULL DEFAULT 0"),
            ("is_active",     "BOOLEAN DEFAULT TRUE"),
            ("updated_at",    "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_by_id", "INTEGER"),
            ("created_by_id", "INTEGER"),
        ]:
            try:
                conn.execute(text(f'ALTER TABLE "{s}".production_outputs ADD COLUMN IF NOT EXISTS {col} {coldef}'))
                conn.commit()
            except Exception:
                conn.rollback()
        print(f"  ✅ production_outputs OK ({s})")

        # ── 10. machine_loss_inputs ──────────────────────────────────────────
        # FK loss_l1/2/3_id ke master_machine_losses_lvl_X (flat tables)
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".machine_loss_inputs (
                id               SERIAL PRIMARY KEY,
                date             TIMESTAMP NOT NULL,
                line_id          INTEGER NOT NULL
                                   REFERENCES "{s}".master_lines(id)  ON DELETE RESTRICT,
                shift_id         INTEGER NOT NULL
                                   REFERENCES "{s}".master_shifts(id) ON DELETE RESTRICT,
                feed_code_id     INTEGER
                                   REFERENCES "{s}".master_feed_codes(id) ON DELETE SET NULL,
                loss_l1_id       INTEGER
                                   REFERENCES "{s}".master_machine_losses_lvl_1(machine_losses_lvl_1_id)
                                   ON DELETE RESTRICT,
                loss_l2_id       INTEGER
                                   REFERENCES "{s}".master_machine_losses_lvl_2(machine_losses_lvl_2_id)
                                   ON DELETE RESTRICT,
                loss_l3_id       INTEGER
                                   REFERENCES "{s}".master_machine_losses_lvl_3(machine_losses_lvl_3_id)
                                   ON DELETE RESTRICT,
                time_from        VARCHAR(8),
                time_to          VARCHAR(8),
                duration_minutes FLOAT NOT NULL,
                remarks          VARCHAR(500),
                is_active        BOOLEAN DEFAULT TRUE,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id    INTEGER,
                updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id    INTEGER
            )
        """))
        conn.commit()
        for col, coldef in [
            ("feed_code_id",  "INTEGER"),
            ("loss_l1_id",    "INTEGER"),
            ("loss_l2_id",    "INTEGER"),
            ("loss_l3_id",    "INTEGER"),
            ("time_from",     "VARCHAR(8)"),
            ("time_to",       "VARCHAR(8)"),
            ("remarks",       "VARCHAR(500)"),
            ("is_active",     "BOOLEAN DEFAULT TRUE"),
            ("updated_at",    "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_by_id", "INTEGER"),
            ("created_by_id", "INTEGER"),
        ]:
            try:
                conn.execute(text(f'ALTER TABLE "{s}".machine_loss_inputs ADD COLUMN IF NOT EXISTS {col} {coldef}'))
                conn.commit()
            except Exception:
                conn.rollback()
        print(f"  ✅ machine_loss_inputs OK ({s})")

        # ── 11. merged_lines ─────────────────────────────────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".merged_lines (
                id            SERIAL PRIMARY KEY,
                name          VARCHAR(100) NOT NULL,
                code          VARCHAR(50),
                remarks       VARCHAR(500),
                is_active     BOOLEAN DEFAULT TRUE,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id INTEGER,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id INTEGER
            )
        """))
        conn.commit()
        print(f"  ✅ merged_lines OK ({s})")

        # ── 12. merged_line_details ──────────────────────────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".merged_line_details (
                merged_line_id INTEGER NOT NULL
                                 REFERENCES "{s}".merged_lines(id) ON DELETE CASCADE,
                line_id        INTEGER NOT NULL
                                 REFERENCES "{s}".master_lines(id) ON DELETE CASCADE,
                PRIMARY KEY (merged_line_id, line_id)
            )
        """))
        conn.commit()
        print(f"  ✅ merged_line_details OK ({s})")

        print(f"  ✅ Schema {s} migration complete")


def migrate_equipment_tree(schema_name: str) -> None:
    """Add master_equipment_tree table — safe to run multiple times."""
    schema_engine = get_schema_engine(schema_name)
    s = schema_name
    with schema_engine.connect() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".master_equipment_tree (
                id               SERIAL PRIMARY KEY,
                sistem           VARCHAR(200) NOT NULL,
                sub_sistem       VARCHAR(200),
                unit_mesin       VARCHAR(200),
                bagian_mesin     VARCHAR(200),
                spare_part       VARCHAR(200),
                spesifikasi      VARCHAR(500),
                sku              VARCHAR(100),
                bu               VARCHAR(50),
                is_verified      BOOLEAN NOT NULL DEFAULT FALSE,
                verified_by_id   INTEGER,
                verified_at      TIMESTAMP,
                remarks          VARCHAR(500),
                is_active        BOOLEAN NOT NULL DEFAULT TRUE,
                created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
                created_by_id    INTEGER,
                updated_at       TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_by_id    INTEGER
            )
        """))
        conn.commit()
        print(f"  ✅ master_equipment_tree OK ({s})")


def run_all_migrations():
    print("🔄 Running plant schema migrations...")
    schemas = get_all_plant_schemas()
    if not schemas:
        print("  ℹ️  No plants registered.")
        return
    for schema in schemas:
        try:
            migrate_plant_schema(schema)
            migrate_equipment_tree(schema)
        except Exception as e:
            print(f"  ❌ Migration error {schema}: {e}")
    print("✅ All plant schema migrations complete.")


if __name__ == "__main__":
    run_all_migrations()
