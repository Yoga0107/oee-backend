"""
migrate_plant_schema.py
-----------------------
Satu-satunya sumber kebenaran untuk skema tabel plant.
Aman dijalankan berulang kali (idempotent — semua pakai IF NOT EXISTS).

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

        # ── 1. loss_level_1 ─────────────────────────────────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".loss_level_1 (
                id            SERIAL PRIMARY KEY,
                name          VARCHAR(200) NOT NULL,
                description   TEXT,
                sort_order    INTEGER DEFAULT 0,
                is_active     BOOLEAN DEFAULT TRUE,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id INTEGER,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id INTEGER
            )
        """))
        conn.commit()

        # ── 2. loss_level_2 ─────────────────────────────────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".loss_level_2 (
                id            SERIAL PRIMARY KEY,
                level_1_id    INTEGER NOT NULL
                                REFERENCES "{s}".loss_level_1(id) ON DELETE RESTRICT,
                name          VARCHAR(200) NOT NULL,
                description   TEXT,
                sort_order    INTEGER DEFAULT 0,
                is_active     BOOLEAN DEFAULT TRUE,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id INTEGER,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id INTEGER
            )
        """))
        conn.commit()

        # ── 3. loss_level_3 ─────────────────────────────────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".loss_level_3 (
                id            SERIAL PRIMARY KEY,
                level_2_id    INTEGER NOT NULL
                                REFERENCES "{s}".loss_level_2(id) ON DELETE RESTRICT,
                name          VARCHAR(200) NOT NULL,
                description   TEXT,
                sort_order    INTEGER DEFAULT 0,
                is_active     BOOLEAN DEFAULT TRUE,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id INTEGER,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id INTEGER
            )
        """))
        conn.commit()

        # Guard: kolom tambahan di loss_level tables
        for tbl in ["loss_level_1", "loss_level_2", "loss_level_3"]:
            for col, coldef in [
                ("sort_order",    "INTEGER DEFAULT 0"),
                ("is_active",     "BOOLEAN DEFAULT TRUE"),
                ("updated_at",    "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("updated_by_id", "INTEGER"),
            ]:
                try:
                    conn.execute(text(f'ALTER TABLE "{s}".{tbl} ADD COLUMN IF NOT EXISTS {col} {coldef}'))
                    conn.commit()
                except Exception:
                    conn.rollback()

        print(f"  ✅ loss_level_1/2/3 OK ({s})")

        # ── 4. machine_losses ────────────────────────────────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".machine_losses (
                id            SERIAL PRIMARY KEY,
                parent_id     INTEGER REFERENCES "{s}".machine_losses(id) ON DELETE RESTRICT,
                level         SMALLINT NOT NULL CHECK (level IN (1, 2, 3)),
                name          VARCHAR(200) NOT NULL,
                description   TEXT,
                sort_order    INTEGER DEFAULT 0,
                is_active     BOOLEAN DEFAULT TRUE,
                source_id     INTEGER,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id INTEGER,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id INTEGER
            )
        """))
        conn.commit()

        for col, coldef in [
            ("description",   "TEXT"),
            ("is_active",     "BOOLEAN DEFAULT TRUE"),
            ("updated_at",    "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_by_id", "INTEGER"),
            ("created_by_id", "INTEGER"),
            ("source_id",     "INTEGER"),
        ]:
            try:
                conn.execute(text(f'ALTER TABLE "{s}".machine_losses ADD COLUMN IF NOT EXISTS {col} {coldef}'))
                conn.commit()
            except Exception:
                conn.rollback()

        print(f"  ✅ machine_losses OK ({s})")

        # ── 5. Trigger: sync loss_level_1/2/3 → machine_losses ───────────────
        conn.execute(text(f"""
            CREATE OR REPLACE FUNCTION "{s}".sync_machine_losses()
            RETURNS TRIGGER LANGUAGE plpgsql AS $$
            DECLARE
                v_parent_id INTEGER;
            BEGIN
                -- ── loss_level_1 ──────────────────────────────────────────
                IF TG_TABLE_NAME = 'loss_level_1' THEN
                    IF TG_OP = 'DELETE' THEN
                        UPDATE "{s}".machine_losses
                           SET is_active = FALSE
                         WHERE level = 1 AND source_id = OLD.id;
                        RETURN OLD;
                    ELSIF TG_OP = 'UPDATE' THEN
                        UPDATE "{s}".machine_losses
                           SET name       = NEW.name,
                               sort_order = NEW.sort_order,
                               is_active  = NEW.is_active
                         WHERE level = 1 AND source_id = NEW.id;
                        RETURN NEW;
                    ELSE
                        INSERT INTO "{s}".machine_losses
                            (parent_id, level, name, sort_order, is_active, created_by_id, source_id)
                        VALUES (NULL, 1, NEW.name, NEW.sort_order, NEW.is_active, NEW.created_by_id, NEW.id)
                        ON CONFLICT DO NOTHING;
                        RETURN NEW;
                    END IF;

                -- ── loss_level_2 ──────────────────────────────────────────
                ELSIF TG_TABLE_NAME = 'loss_level_2' THEN
                    IF TG_OP = 'DELETE' THEN
                        UPDATE "{s}".machine_losses
                           SET is_active = FALSE
                         WHERE level = 2 AND source_id = OLD.id;
                        RETURN OLD;
                    ELSIF TG_OP = 'UPDATE' THEN
                        UPDATE "{s}".machine_losses
                           SET name       = NEW.name,
                               sort_order = NEW.sort_order,
                               is_active  = NEW.is_active
                         WHERE level = 2 AND source_id = NEW.id;
                        RETURN NEW;
                    ELSE
                        SELECT ml.id INTO v_parent_id
                          FROM "{s}".machine_losses ml
                         WHERE ml.level = 1 AND ml.source_id = NEW.level_1_id
                         LIMIT 1;

                        IF v_parent_id IS NULL THEN
                            SELECT ml.id INTO v_parent_id
                              FROM "{s}".machine_losses ml
                              JOIN "{s}".loss_level_1 l1 ON l1.name = ml.name
                             WHERE ml.level = 1 AND l1.id = NEW.level_1_id
                             LIMIT 1;
                        END IF;

                        INSERT INTO "{s}".machine_losses
                            (parent_id, level, name, sort_order, is_active, created_by_id, source_id)
                        VALUES (v_parent_id, 2, NEW.name, NEW.sort_order, NEW.is_active, NEW.created_by_id, NEW.id)
                        ON CONFLICT DO NOTHING;
                        RETURN NEW;
                    END IF;

                -- ── loss_level_3 ──────────────────────────────────────────
                ELSIF TG_TABLE_NAME = 'loss_level_3' THEN
                    IF TG_OP = 'DELETE' THEN
                        UPDATE "{s}".machine_losses
                           SET is_active = FALSE
                         WHERE level = 3 AND source_id = OLD.id;
                        RETURN OLD;
                    ELSIF TG_OP = 'UPDATE' THEN
                        UPDATE "{s}".machine_losses ml
                           SET name       = NEW.name,
                               sort_order = NEW.sort_order,
                               is_active  = NEW.is_active,
                               parent_id  = CASE
                                   WHEN NEW.level_2_id <> OLD.level_2_id THEN (
                                       SELECT id FROM "{s}".machine_losses
                                        WHERE level = 2 AND source_id = NEW.level_2_id
                                        LIMIT 1
                                   )
                                   ELSE ml.parent_id
                               END
                         WHERE ml.level = 3 AND ml.source_id = NEW.id;
                        RETURN NEW;
                    ELSE
                        SELECT ml.id INTO v_parent_id
                          FROM "{s}".machine_losses ml
                         WHERE ml.level = 2 AND ml.source_id = NEW.level_2_id
                         LIMIT 1;

                        IF v_parent_id IS NULL THEN
                            SELECT ml.id INTO v_parent_id
                              FROM "{s}".machine_losses ml
                              JOIN "{s}".loss_level_2 l2 ON l2.name = ml.name
                             WHERE ml.level = 2 AND l2.id = NEW.level_2_id
                             LIMIT 1;
                        END IF;

                        INSERT INTO "{s}".machine_losses
                            (parent_id, level, name, sort_order, is_active, created_by_id, source_id)
                        VALUES (v_parent_id, 3, NEW.name, NEW.sort_order, NEW.is_active, NEW.created_by_id, NEW.id)
                        ON CONFLICT DO NOTHING;
                        RETURN NEW;
                    END IF;
                END IF;

                RETURN NULL;
            END;
            $$;
        """))
        conn.commit()

        for tbl in ["loss_level_1", "loss_level_2", "loss_level_3"]:
            conn.execute(text(f'DROP TRIGGER IF EXISTS trg_sync_machine_losses_{tbl} ON "{s}".{tbl};'))
            conn.execute(text(f"""
                CREATE TRIGGER trg_sync_machine_losses_{tbl}
                AFTER INSERT OR UPDATE OR DELETE ON "{s}".{tbl}
                FOR EACH ROW EXECUTE FUNCTION "{s}".sync_machine_losses();
            """))
        conn.commit()
        print(f"  ✅ Trigger sync_machine_losses installed ({s})")

        # ── 6. machine_loss_hierarchy ────────────────────────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".machine_loss_hierarchy (
                id                   SERIAL PRIMARY KEY,
                source_level         SMALLINT     NOT NULL DEFAULT 1,
                source_name          VARCHAR(200) NOT NULL DEFAULT '',
                effective_level      SMALLINT     NOT NULL DEFAULT 1,
                parent_hierarchy_id  INTEGER
                                       REFERENCES "{s}".machine_loss_hierarchy(id)
                                       ON DELETE SET NULL,
                level_1_id           INTEGER REFERENCES "{s}".loss_level_1(id) ON DELETE CASCADE,
                level_2_id           INTEGER REFERENCES "{s}".loss_level_2(id) ON DELETE CASCADE,
                level_3_id           INTEGER REFERENCES "{s}".loss_level_3(id) ON DELETE CASCADE,
                is_unparented        BOOLEAN DEFAULT FALSE,
                notes                VARCHAR(500),
                sort_order           INTEGER DEFAULT 0,
                is_active            BOOLEAN DEFAULT TRUE,
                created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id        INTEGER,
                updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id        INTEGER
            )
        """))
        conn.commit()

        # Guard: kolom tambahan machine_loss_hierarchy
        hierarchy_columns = [
            ("source_level",        "SMALLINT NOT NULL DEFAULT 1"),
            ("source_name",         "VARCHAR(200) NOT NULL DEFAULT ''"),
            ("effective_level",     "SMALLINT NOT NULL DEFAULT 1"),
            ("is_unparented",       "BOOLEAN DEFAULT FALSE"),
            ("notes",               "VARCHAR(500)"),
            ("parent_hierarchy_id", f'INTEGER REFERENCES "{s}".machine_loss_hierarchy(id) ON DELETE SET NULL'),
            ("level_1_id",          f'INTEGER REFERENCES "{s}".loss_level_1(id) ON DELETE CASCADE'),
            ("level_2_id",          f'INTEGER REFERENCES "{s}".loss_level_2(id) ON DELETE CASCADE'),
            ("level_3_id",          f'INTEGER REFERENCES "{s}".loss_level_3(id) ON DELETE CASCADE'),
        ]
        for col, coldef in hierarchy_columns:
            try:
                conn.execute(text(f'ALTER TABLE "{s}".machine_loss_hierarchy ADD COLUMN IF NOT EXISTS {col} {coldef}'))
                conn.commit()
            except Exception:
                conn.rollback()

        print(f"  ✅ machine_loss_hierarchy OK ({s})")

        # ── 7. master_shifts ─────────────────────────────────────────────────
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

        # ── 8. master_feed_codes ─────────────────────────────────────────────
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

        # ── 9. master_lines ──────────────────────────────────────────────────
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

        # FK constraint untuk current_feed_code_id (jika belum ada)
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

        # ── 10. master_standard_throughputs ──────────────────────────────────
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

        # ── 11. production_outputs ───────────────────────────────────────────
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".production_outputs (
                id                   SERIAL PRIMARY KEY,
                date                 TIMESTAMP NOT NULL,
                line_id              INTEGER NOT NULL
                                       REFERENCES "{s}".master_lines(id)  ON DELETE RESTRICT,
                shift_id             INTEGER NOT NULL
                                       REFERENCES "{s}".master_shifts(id) ON DELETE RESTRICT,
                feed_code_id         INTEGER
                                       REFERENCES "{s}".master_feed_codes(id) ON DELETE SET NULL,
                production_plan      INTEGER,
                finished_goods       INTEGER NOT NULL DEFAULT 0,
                downgraded_product   INTEGER NOT NULL DEFAULT 0,
                wip                  INTEGER NOT NULL DEFAULT 0,
                remix                INTEGER NOT NULL DEFAULT 0,
                reject_product       INTEGER NOT NULL DEFAULT 0,
                actual_output        INTEGER NOT NULL DEFAULT 0,
                good_product         INTEGER NOT NULL DEFAULT 0,
                quality_rate         FLOAT   NOT NULL DEFAULT 0,
                remarks              VARCHAR(500),
                is_active            BOOLEAN DEFAULT TRUE,
                created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id        INTEGER,
                updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id        INTEGER
            )
        """))
        conn.commit()

        # Guard: kolom baru jika tabel sudah ada dari versi lama
        for col, coldef in [
            ("finished_goods",     "INTEGER NOT NULL DEFAULT 0"),
            ("downgraded_product", "INTEGER NOT NULL DEFAULT 0"),
            ("wip",                "INTEGER NOT NULL DEFAULT 0"),
            ("remix",              "INTEGER NOT NULL DEFAULT 0"),
            ("actual_output",      "INTEGER NOT NULL DEFAULT 0"),
            ("good_product",       "INTEGER NOT NULL DEFAULT 0"),
            ("quality_rate",       "FLOAT NOT NULL DEFAULT 0"),
            ("is_active",          "BOOLEAN DEFAULT TRUE"),
            ("updated_at",         "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_by_id",      "INTEGER"),
            ("created_by_id",      "INTEGER"),
        ]:
            try:
                conn.execute(text(f'ALTER TABLE "{s}".production_outputs ADD COLUMN IF NOT EXISTS {col} {coldef}'))
                conn.commit()
            except Exception:
                conn.rollback()

        print(f"  ✅ production_outputs OK ({s})")

        # ── 12. machine_loss_inputs ──────────────────────────────────────────
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
                loss_l1_id       INTEGER REFERENCES "{s}".machine_losses(id) ON DELETE RESTRICT,
                loss_l2_id       INTEGER REFERENCES "{s}".machine_losses(id) ON DELETE RESTRICT,
                loss_l3_id       INTEGER REFERENCES "{s}".machine_losses(id) ON DELETE RESTRICT,
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
            ("feed_code_id",     "INTEGER"),
            ("loss_l1_id",       "INTEGER"),
            ("loss_l2_id",       "INTEGER"),
            ("loss_l3_id",       "INTEGER"),
            ("time_from",        "VARCHAR(8)"),
            ("time_to",          "VARCHAR(8)"),
            ("remarks",          "VARCHAR(500)"),
            ("is_active",        "BOOLEAN DEFAULT TRUE"),
            ("updated_at",       "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_by_id",    "INTEGER"),
            ("created_by_id",    "INTEGER"),
        ]:
            try:
                conn.execute(text(f'ALTER TABLE "{s}".machine_loss_inputs ADD COLUMN IF NOT EXISTS {col} {coldef}'))
                conn.commit()
            except Exception:
                conn.rollback()

        print(f"  ✅ machine_loss_inputs OK ({s})")

        print(f"  ✅ Schema {s} migration complete")


def run_all_migrations():
    print("🔄 Running plant schema migrations...")
    schemas = get_all_plant_schemas()
    if not schemas:
        print("  ℹ️  No plants registered.")
        return
    for schema in schemas:
        try:
            migrate_plant_schema(schema)
        except Exception as e:
            print(f"  ❌ Migration error {schema}: {e}")
    print("✅ All plant schema migrations complete.")


if __name__ == "__main__":
    run_all_migrations()
