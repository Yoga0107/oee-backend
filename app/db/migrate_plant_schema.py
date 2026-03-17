"""
migrate_plant_schema.py
-----------------------
Run once after model updates:

    python -m app.db.migrate_plant_schema

Or called automatically from lifespan in main.py.

Machine Loss architecture:
  loss_level_1   → L1 master input table
  loss_level_2   → L2 master input table (FK → loss_level_1)
  loss_level_3   → L3 master input table (FK → loss_level_2)
  machine_losses → aggregation table, synced via PostgreSQL trigger
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

        # Guard: add missing columns to loss_level tables (for older DBs)
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

        # ── 4. machine_losses (aggregation table) ────────────────────────────
        # The existing table may use the OLD self-referencing schema
        # (parent_id, level, name) WITHOUT level_1_id/level_2_id/level_3_id.
        # We keep it as-is for backward compatibility.
        # The trigger below works with WHATEVER columns exist.
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".machine_losses (
                id         SERIAL PRIMARY KEY,
                parent_id  INTEGER REFERENCES "{s}".machine_losses(id) ON DELETE RESTRICT,
                level      SMALLINT NOT NULL CHECK (level IN (1, 2, 3)),
                name       VARCHAR(200) NOT NULL,
                description TEXT,
                sort_order INTEGER DEFAULT 0,
                is_active  BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id INTEGER
            )
        """))
        conn.commit()

        # Guard: add missing columns to existing machine_losses
        for col, coldef in [
            ("description",    "TEXT"),
            ("is_active",      "BOOLEAN DEFAULT TRUE"),
            ("updated_at",     "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_by_id",  "INTEGER"),
            ("created_by_id",  "INTEGER"),
            # source_id: stores the original loss_level_X.id for reliable lookup
            ("source_id",      "INTEGER"),
        ]:
            try:
                conn.execute(text(f'ALTER TABLE "{s}".machine_losses ADD COLUMN IF NOT EXISTS {col} {coldef}'))
                conn.commit()
            except Exception:
                conn.rollback()

        print(f"  ✅ machine_losses OK ({s})")

        # ── 5. PostgreSQL trigger: sync loss_level_1/2/3 → machine_losses ────
        # Uses the ORIGINAL machine_losses schema (parent_id + level + name).
        # Also stores source_id = the loss_level_X.id for reliable backend lookups.
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
                    ELSE -- INSERT
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
                    ELSE -- INSERT: find L1 parent in machine_losses
                        SELECT ml.id INTO v_parent_id
                          FROM "{s}".machine_losses ml
                         WHERE ml.level = 1 AND ml.source_id = NEW.level_1_id
                         LIMIT 1;

                        -- Fallback: match by name if source_id not set yet
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
                        UPDATE "{s}".machine_losses
                           SET name       = NEW.name,
                               sort_order = NEW.sort_order,
                               is_active  = NEW.is_active
                         WHERE level = 3 AND source_id = NEW.id;
                        RETURN NEW;
                    ELSE -- INSERT: find L2 parent in machine_losses
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
                id         SERIAL PRIMARY KEY,
                sort_order INTEGER DEFAULT 0,
                is_active  BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_id INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_id INTEGER
            )
        """))
        conn.commit()

        hierarchy_columns = [
            ("source_level",        "SMALLINT"),
            ("source_name",         "VARCHAR(200)"),
            ("effective_level",     "SMALLINT"),
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

        try:
            conn.execute(text(f"""
                UPDATE "{s}".machine_loss_hierarchy
                   SET source_level = 1, effective_level = 1, source_name = 'unknown'
                 WHERE source_level IS NULL OR effective_level IS NULL OR source_name IS NULL
            """))
            conn.commit()
        except Exception:
            conn.rollback()

        for col in ["source_level", "effective_level", "source_name"]:
            try:
                conn.execute(text(f'ALTER TABLE "{s}".machine_loss_hierarchy ALTER COLUMN {col} SET NOT NULL'))
                conn.commit()
            except Exception:
                conn.rollback()

        print(f"  ✅ machine_loss_hierarchy OK ({s})")

        # ── 7. Guard: is_active on other master tables ────────────────────────
        for tbl in ["master_shifts", "master_feed_codes", "master_lines"]:
            try:
                conn.execute(text(f'ALTER TABLE "{s}".{tbl} ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE'))
                conn.commit()
            except Exception:
                conn.rollback()

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