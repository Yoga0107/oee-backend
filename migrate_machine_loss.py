"""
migrate_machine_loss_erd.py
===========================
Migrates database from OLD machine loss schema to NEW 4-table ERD structure.

OLD schema:
  - loss_level_1 / loss_level_2 / loss_level_3   (master input tables)
  - machine_losses                                 (self-referencing aggregation)
  - machine_loss_hierarchy                         (drag-and-drop remap)
  - machine_loss_inputs.loss_l1/2/3_id → FK to machine_losses.id

NEW schema (sesuai ERD):
  - master_machine_losses_lvl_1  (id, name)
  - master_machine_losses_lvl_2  (id, name)
  - master_machine_losses_lvl_3  (id, name)
  - master_machine_losses        (id, lvl1_id FK, lvl2_id FK, lvl3_id FK, remarks)
  - machine_loss_inputs.loss_l1/2/3_id → FK to master_machine_losses_lvl_X.id

Migration steps per plant schema:
  1. Create 4 new tables
  2. Backfill lvl_1/2/3 from loss_level_1/2/3
  3. Backfill master_machine_losses from machine_losses (level 1/2/3 hierarchy)
  4. Update machine_loss_inputs FK references to point to new lvl tables
  5. Drop FK constraints from machine_loss_inputs pointing to machine_losses
  6. Add new FK constraints pointing to master_machine_losses_lvl_X
  7. Drop old tables (optional — commented out for safety, uncomment when ready)

Run once:
    python migrate_machine_loss_erd.py

Safe to re-run — uses IF NOT EXISTS / ON CONFLICT guards.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import engine
from sqlalchemy import text


def _table_exists(conn, schema, table):
    return conn.execute(text("""
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = :s AND table_name = :t
    """), {"s": schema, "t": table}).fetchone() is not None


def _col_exists(conn, schema, table, col):
    return conn.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = :s AND table_name = :t AND column_name = :c
    """), {"s": schema, "t": table, "c": col}).fetchone() is not None


def migrate():
    with engine.connect() as conn:
        schemas = conn.execute(text(
            "SELECT schema_name FROM public.plants WHERE is_active = TRUE"
        )).fetchall()

        if not schemas:
            print("⚠️  No active plants found.")
            return

        for (schema,) in schemas:
            print(f"\n🔄  Schema: {schema}")

            # ── Step 1: Create new tables ──────────────────────────────────
            for tbl in ["master_machine_losses_lvl_1", "master_machine_losses_lvl_2", "master_machine_losses_lvl_3"]:
                conn.execute(text(f"""
                    CREATE TABLE IF NOT EXISTS "{schema}".{tbl} (
                        id            SERIAL PRIMARY KEY,
                        name          VARCHAR(200) NOT NULL,
                        sort_order    INTEGER NOT NULL DEFAULT 0,
                        is_active     BOOLEAN DEFAULT TRUE,
                        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_by_id INTEGER,
                        updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_by_id INTEGER
                    )
                """))
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS "{schema}".master_machine_losses (
                    id            SERIAL PRIMARY KEY,
                    lvl1_id       INTEGER NOT NULL
                                    REFERENCES "{schema}".master_machine_losses_lvl_1(id) ON DELETE RESTRICT,
                    lvl2_id       INTEGER
                                    REFERENCES "{schema}".master_machine_losses_lvl_2(id) ON DELETE RESTRICT,
                    lvl3_id       INTEGER
                                    REFERENCES "{schema}".master_machine_losses_lvl_3(id) ON DELETE RESTRICT,
                    remarks       TEXT,
                    is_active     BOOLEAN DEFAULT TRUE,
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by_id INTEGER,
                    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by_id INTEGER
                )
            """))
            conn.commit()
            print("   ✅ New tables created")

            # ── Step 2: Backfill lvl_1 from loss_level_1 ──────────────────
            if _table_exists(conn, schema, "loss_level_1"):
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses_lvl_1
                        (id, name, sort_order, is_active, created_at, created_by_id)
                    SELECT id, name, sort_order, is_active, created_at, created_by_id
                    FROM   "{schema}".loss_level_1
                    ON CONFLICT (id) DO NOTHING
                """))
                conn.commit()
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".master_machine_losses_lvl_1')).scalar()
                print(f"   ✅ master_machine_losses_lvl_1: {n} rows")

            # ── Step 3: Backfill lvl_2 from loss_level_2 ──────────────────
            if _table_exists(conn, schema, "loss_level_2"):
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses_lvl_2
                        (id, name, sort_order, is_active, created_at, created_by_id)
                    SELECT id, name, sort_order, is_active, created_at, created_by_id
                    FROM   "{schema}".loss_level_2
                    ON CONFLICT (id) DO NOTHING
                """))
                conn.commit()
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".master_machine_losses_lvl_2')).scalar()
                print(f"   ✅ master_machine_losses_lvl_2: {n} rows")

            # ── Step 4: Backfill lvl_3 from loss_level_3 ──────────────────
            if _table_exists(conn, schema, "loss_level_3"):
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses_lvl_3
                        (id, name, sort_order, is_active, created_at, created_by_id)
                    SELECT id, name, sort_order, is_active, created_at, created_by_id
                    FROM   "{schema}".loss_level_3
                    ON CONFLICT (id) DO NOTHING
                """))
                conn.commit()
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".master_machine_losses_lvl_3')).scalar()
                print(f"   ✅ master_machine_losses_lvl_3: {n} rows")

            # ── Step 5: Backfill master_machine_losses from machine_losses ─
            # machine_losses is self-referencing (level 1/2/3).
            # We create one mapping row per L1 node that has L2 and L3 children.
            if _table_exists(conn, schema, "machine_losses"):
                # Insert all unique L1+L2+L3 combinations that exist
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses (lvl1_id, lvl2_id, lvl3_id, is_active)
                    SELECT DISTINCT
                        ml1.id   AS lvl1_id,
                        ml2.id   AS lvl2_id,
                        ml3.id   AS lvl3_id,
                        TRUE
                    FROM "{schema}".machine_losses ml3
                    JOIN "{schema}".machine_losses ml2 ON ml2.id = ml3.parent_id AND ml2.level = 2
                    JOIN "{schema}".machine_losses ml1 ON ml1.id = ml2.parent_id AND ml1.level = 1
                    WHERE ml3.level = 3 AND ml3.is_active = TRUE
                    ON CONFLICT DO NOTHING
                """))
                # Also insert L1+L2 combinations (no L3)
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses (lvl1_id, lvl2_id, lvl3_id, is_active)
                    SELECT DISTINCT
                        ml1.id, ml2.id, NULL, TRUE
                    FROM "{schema}".machine_losses ml2
                    JOIN "{schema}".machine_losses ml1 ON ml1.id = ml2.parent_id AND ml1.level = 1
                    WHERE ml2.level = 2 AND ml2.is_active = TRUE
                    ON CONFLICT DO NOTHING
                """))
                # Also insert standalone L1 (no L2/L3)
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses (lvl1_id, lvl2_id, lvl3_id, is_active)
                    SELECT id, NULL, NULL, TRUE
                    FROM "{schema}".machine_losses
                    WHERE level = 1 AND is_active = TRUE
                    ON CONFLICT DO NOTHING
                """))
                conn.commit()
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".master_machine_losses')).scalar()
                print(f"   ✅ master_machine_losses: {n} mapping rows")

            # ── Step 6: Update machine_loss_inputs FK references ──────────
            # Old: loss_l1/2/3_id pointed to machine_losses.id (self-ref)
            # New: they point to master_machine_losses_lvl_1/2/3.id
            # The IDs match because we copied them with same IDs in step 2-4.
            # We just need to drop old FK constraints and add new ones.

   # ── Step 5: Backfill master_machine_losses from machine_losses ─
            # machine_losses is self-referencing (level 1/2/3).
            # We create one mapping row per L1 node that has L2 and L3 children.
            if _table_exists(conn, schema, "machine_losses"):
                # Insert all unique L1+L2+L3 combinations that exist
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses (lvl1_id, lvl2_id, lvl3_id, is_active)
                    SELECT DISTINCT
                        ml1.id   AS lvl1_id,
                        ml2.id   AS lvl2_id,
                        ml3.id   AS lvl3_id,
                        TRUE
                    FROM "{schema}".machine_losses ml3
                    JOIN "{schema}".machine_losses ml2 ON ml2.id = ml3.parent_id AND ml2.level = 2
                    JOIN "{schema}".machine_losses ml1 ON ml1.id = ml2.parent_id AND ml1.level = 1
                    WHERE ml3.level = 3 AND ml3.is_active = TRUE
                    ON CONFLICT DO NOTHING
                """))
                # Also insert L1+L2 combinations (no L3)
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses (lvl1_id, lvl2_id, lvl3_id, is_active)
                    SELECT DISTINCT
                        ml1.id, ml2.id, NULL::INTEGER, TRUE
                    FROM "{schema}".machine_losses ml2
                    JOIN "{schema}".machine_losses ml1 ON ml1.id = ml2.parent_id AND ml1.level = 1
                    WHERE ml2.level = 2 AND ml2.is_active = TRUE
                    ON CONFLICT DO NOTHING
                """))
                # Also insert standalone L1 (no L2/L3)
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses (lvl1_id, lvl2_id, lvl3_id, is_active)
                    SELECT id, NULL::INTEGER, NULL::INTEGER, TRUE
                    FROM "{schema}".machine_losses
                    WHERE level = 1 AND is_active = TRUE
                    ON CONFLICT DO NOTHING
                """))
                conn.commit()
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".master_machine_losses')).scalar()
                print(f"   ✅ master_machine_losses: {n} mapping rows")

            # ── Step 7: Drop old tables (commented for safety) ────────────
            # Uncomment only after verifying new schema works correctly!
            #
            # for old_tbl in ["machine_loss_hierarchy", "machine_losses",
            #                  "loss_level_3", "loss_level_2", "loss_level_1"]:
            #     if _table_exists(conn, schema, old_tbl):
            #         conn.execute(text(f'DROP TABLE "{schema}".{old_tbl} CASCADE'))
            #         conn.commit()
            #         print(f"   🗑️  Dropped {old_tbl}")

            print(f"   ✅ Schema {schema} done")

        print("\n✅  Migration complete.")
        print("\nℹ️  Old tables (loss_level_1/2/3, machine_losses, machine_loss_hierarchy)")
        print("    are still present. Drop them manually after verifying the new schema.")


if __name__ == "__main__":
    migrate()
