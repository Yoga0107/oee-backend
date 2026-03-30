"""
migrate_machine_loss.py
=======================
Migrasi dari schema LAMA ke schema BARU sesuai ERD.

Struktur BARU (sesuai ERD):
  - master_machine_losses_lvl_1 : FLAT (machine_losses_lvl_1_id, name)
  - master_machine_losses_lvl_2 : FLAT (machine_losses_lvl_2_id, name)
  - master_machine_losses_lvl_3 : FLAT (machine_losses_lvl_3_id, name)
  - master_machine_losses       : hierarki di sini
                                  (machine_losses_lvl_1_id FK, _lvl_2_id FK, _lvl_3_id FK)

OLD tables yang akan di-drop:
  - loss_level_1 / loss_level_2 / loss_level_3
  - machine_losses  (self-referencing)
  - machine_loss_hierarchy

Run: python migrate_machine_loss.py
Aman di-re-run.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import engine
from app.db.migrate_plant_schema import migrate_plant_schema
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


def _drop_and_recreate_master_machine_losses(conn, schema):
    """
    DROP master_machine_losses (CASCADE) lalu recreate dengan struktur ERD baru.
    Dipanggil jika terdeteksi tabel masih struktur lama.
    """
    try:
        conn.execute(text(f'DROP TABLE "{schema}".master_machine_losses CASCADE'))
        conn.commit()
        print(f"  Dropped master_machine_losses (old structure)")
    except Exception as e:
        conn.rollback()
        print(f"  ERROR: Gagal drop master_machine_losses: {e}")
        return False

    conn.execute(text(f"""
        CREATE TABLE "{schema}".master_machine_losses (
            machine_losses_id       SERIAL PRIMARY KEY,
            machine_losses_lvl_1_id INTEGER NOT NULL
                                      REFERENCES "{schema}".master_machine_losses_lvl_1(machine_losses_lvl_1_id)
                                      ON DELETE RESTRICT,
            machine_losses_lvl_2_id INTEGER
                                      REFERENCES "{schema}".master_machine_losses_lvl_2(machine_losses_lvl_2_id)
                                      ON DELETE RESTRICT,
            machine_losses_lvl_3_id INTEGER
                                      REFERENCES "{schema}".master_machine_losses_lvl_3(machine_losses_lvl_3_id)
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
    print(f"  Recreated master_machine_losses (ERD structure)")
    return True


def _drop_and_recreate_lvl_tables(conn, schema):
    """
    DROP master_machine_losses_lvl_1/2/3 yang mungkin masih struktur lama
    (punya kolom lvl1_id/lvl2_id atau kolom lain selain id & name),
    lalu recreate sebagai flat table.
    """
    # Harus drop master_machine_losses dulu karena ada FK ke lvl tables
    if _table_exists(conn, schema, "master_machine_losses"):
        try:
            conn.execute(text(f'DROP TABLE "{schema}".master_machine_losses CASCADE'))
            conn.commit()
            print(f"  Dropped master_machine_losses (before rebuilding lvl tables)")
        except Exception as e:
            conn.rollback()
            print(f"  ERROR drop master_machine_losses: {e}")

    for tbl, pk_col in [
        ("master_machine_losses_lvl_1", "machine_losses_lvl_1_id"),
        ("master_machine_losses_lvl_2", "machine_losses_lvl_2_id"),
        ("master_machine_losses_lvl_3", "machine_losses_lvl_3_id"),
    ]:
        if _table_exists(conn, schema, tbl):
            # Cek apakah punya kolom ekstra (bukan flat)
            has_extra = (
                _col_exists(conn, schema, tbl, "lvl1_id") or
                _col_exists(conn, schema, tbl, "lvl2_id") or
                _col_exists(conn, schema, tbl, "level_1_id") or
                _col_exists(conn, schema, tbl, "level_2_id") or
                _col_exists(conn, schema, tbl, "description") or
                _col_exists(conn, schema, tbl, "sort_order")
            )
            if has_extra:
                try:
                    conn.execute(text(f'DROP TABLE "{schema}".{tbl} CASCADE'))
                    conn.commit()
                    print(f"  Dropped {tbl} (old structure with extra columns)")
                except Exception as e:
                    conn.rollback()
                    print(f"  ERROR drop {tbl}: {e}")
                    continue

                conn.execute(text(f"""
                    CREATE TABLE "{schema}".{tbl} (
                        {pk_col} SERIAL PRIMARY KEY,
                        name     VARCHAR(200) NOT NULL
                    )
                """))
                conn.commit()
                print(f"  Recreated {tbl} (flat: {pk_col}, name)")


def migrate():
    with engine.connect() as conn:
        schemas = conn.execute(text(
            "SELECT schema_name FROM public.plants WHERE is_active = TRUE"
        )).fetchall()

        if not schemas:
            print("No active plants found.")
            return

        for (schema,) in schemas:
            print(f"\n=== Schema: {schema} ===")

            # ── Step 1: Rebuild lvl tables jika masih struktur lama ───────
            print("  Step 1: Checking & rebuilding lvl tables if needed...")
            _drop_and_recreate_lvl_tables(conn, schema)

            # ── Step 2: Jalankan migrate_plant_schema (idempotent) ────────
            # Ini akan CREATE IF NOT EXISTS semua tabel baru yang belum ada
            print("  Step 2: Running migrate_plant_schema...")
            migrate_plant_schema(schema)

            # ── Step 3: Periksa master_machine_losses ─────────────────────
            # Setelah Step 2, pastikan strukturnya sudah benar
            print("  Step 3: Checking master_machine_losses structure...")
            if _table_exists(conn, schema, "master_machine_losses"):
                is_old_self_ref = _col_exists(conn, schema, "master_machine_losses", "level")
                is_old_col_name = _col_exists(conn, schema, "master_machine_losses", "lvl1_id")
                is_correct      = _col_exists(conn, schema, "master_machine_losses", "machine_losses_lvl_1_id")

                if is_old_self_ref or is_old_col_name:
                    print(f"  WARNING: master_machine_losses masih struktur lama, rebuild...")
                    _drop_and_recreate_master_machine_losses(conn, schema)
                elif is_correct:
                    print(f"  OK master_machine_losses sudah struktur ERD yang benar")
                else:
                    print(f"  WARNING: master_machine_losses struktur tidak dikenal, rebuild...")
                    _drop_and_recreate_master_machine_losses(conn, schema)

            # ── Step 4: Backfill lvl_1 dari loss_level_1 ─────────────────
            print("  Step 4: Backfill master_machine_losses_lvl_1...")
            if _table_exists(conn, schema, "loss_level_1"):
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses_lvl_1
                        (machine_losses_lvl_1_id, name)
                    SELECT id, name
                    FROM   "{schema}".loss_level_1
                    ON CONFLICT (machine_losses_lvl_1_id) DO NOTHING
                """))
                conn.commit()
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".master_machine_losses_lvl_1')).scalar()
                print(f"  OK {n} rows")
            else:
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".master_machine_losses_lvl_1')).scalar()
                print(f"  loss_level_1 tidak ada, existing: {n} rows")

            # ── Step 5: Backfill lvl_2 dari loss_level_2 ─────────────────
            print("  Step 5: Backfill master_machine_losses_lvl_2...")
            if _table_exists(conn, schema, "loss_level_2"):
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses_lvl_2
                        (machine_losses_lvl_2_id, name)
                    SELECT id, name
                    FROM   "{schema}".loss_level_2
                    ON CONFLICT (machine_losses_lvl_2_id) DO NOTHING
                """))
                conn.commit()
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".master_machine_losses_lvl_2')).scalar()
                print(f"  OK {n} rows")
            else:
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".master_machine_losses_lvl_2')).scalar()
                print(f"  loss_level_2 tidak ada, existing: {n} rows")

            # ── Step 6: Backfill lvl_3 dari loss_level_3 ─────────────────
            print("  Step 6: Backfill master_machine_losses_lvl_3...")
            if _table_exists(conn, schema, "loss_level_3"):
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses_lvl_3
                        (machine_losses_lvl_3_id, name)
                    SELECT id, name
                    FROM   "{schema}".loss_level_3
                    ON CONFLICT (machine_losses_lvl_3_id) DO NOTHING
                """))
                conn.commit()
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".master_machine_losses_lvl_3')).scalar()
                print(f"  OK {n} rows")
            else:
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".master_machine_losses_lvl_3')).scalar()
                print(f"  loss_level_3 tidak ada, existing: {n} rows")

            # ── Step 7: Backfill master_machine_losses dari machine_losses lama
            # machine_losses lama: self-referencing dengan kolom level & source_id
            # source_id = ID di loss_level_X yang sesuai
            print("  Step 7: Backfill master_machine_losses...")
            if _table_exists(conn, schema, "machine_losses") and \
               _col_exists(conn, schema, "machine_losses", "source_id"):
                # L1 + L2 + L3 combinations
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses
                        (machine_losses_lvl_1_id, machine_losses_lvl_2_id, machine_losses_lvl_3_id, is_active)
                    SELECT DISTINCT
                        ml1.source_id,
                        ml2.source_id,
                        ml3.source_id,
                        TRUE
                    FROM "{schema}".machine_losses ml3
                    JOIN "{schema}".machine_losses ml2 ON ml2.id = ml3.parent_id AND ml2.level = 2
                    JOIN "{schema}".machine_losses ml1 ON ml1.id = ml2.parent_id AND ml1.level = 1
                    WHERE ml3.level = 3 AND ml3.is_active = TRUE
                      AND ml1.source_id IS NOT NULL
                      AND ml2.source_id IS NOT NULL
                      AND ml3.source_id IS NOT NULL
                    ON CONFLICT DO NOTHING
                """))
                # L1 + L2 (no L3)
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses
                        (machine_losses_lvl_1_id, machine_losses_lvl_2_id, machine_losses_lvl_3_id, is_active)
                    SELECT DISTINCT
                        ml1.source_id, ml2.source_id, NULL::INTEGER, TRUE
                    FROM "{schema}".machine_losses ml2
                    JOIN "{schema}".machine_losses ml1 ON ml1.id = ml2.parent_id AND ml1.level = 1
                    WHERE ml2.level = 2 AND ml2.is_active = TRUE
                      AND ml1.source_id IS NOT NULL
                      AND ml2.source_id IS NOT NULL
                    ON CONFLICT DO NOTHING
                """))
                # Standalone L1
                conn.execute(text(f"""
                    INSERT INTO "{schema}".master_machine_losses
                        (machine_losses_lvl_1_id, machine_losses_lvl_2_id, machine_losses_lvl_3_id, is_active)
                    SELECT source_id, NULL::INTEGER, NULL::INTEGER, TRUE
                    FROM "{schema}".machine_losses
                    WHERE level = 1 AND is_active = TRUE
                      AND source_id IS NOT NULL
                    ON CONFLICT DO NOTHING
                """))
                conn.commit()
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".master_machine_losses')).scalar()
                print(f"  OK {n} mapping rows")
            else:
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".master_machine_losses')).scalar()
                print(f"  machine_losses tidak ada / tidak punya source_id, existing: {n} rows")

            # ── Step 8: Drop semua tabel lama ─────────────────────────────
            print("  Step 8: Dropping old tables...")
            old_tables = [
                "machine_loss_hierarchy",
                "machine_losses",
                "loss_level_3",
                "loss_level_2",
                "loss_level_1",
            ]
            for old_tbl in old_tables:
                if _table_exists(conn, schema, old_tbl):
                    try:
                        conn.execute(text(f'DROP TABLE "{schema}".{old_tbl} CASCADE'))
                        conn.commit()
                        print(f"  Dropped {old_tbl}")
                    except Exception as e:
                        conn.rollback()
                        print(f"  WARNING: Could not drop {old_tbl}: {e}")
                else:
                    print(f"  {old_tbl} tidak ada, skip")

            print(f"  === Schema {schema} DONE ===")

        print("\nMigration complete.")


if __name__ == "__main__":
    migrate()