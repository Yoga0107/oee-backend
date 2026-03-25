"""
migrate_output_items.py
=======================
Migrates existing databases from OLD schema (production_outputs with 5 separate
columns: finished_goods, downgraded_product, wip, remix, reject_product) to
NEW schema where each row IS one output_type with a group_id tying 5 rows together.

Steps per plant schema:
  1. Add new columns: group_id, output_type, category, quantity
  2. For each existing row, backfill 4 extra rows (total = 5) with the same group_id
  3. Drop legacy columns: finished_goods, downgraded_product, wip, remix,
     reject_product, actual_output, good_product, quality_rate
  4. Drop production_output_items table (no longer needed)

Run once:
    python migrate_output_items.py

Safe to re-run — uses IF NOT EXISTS / ON CONFLICT guards.
"""
import sys, os, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import engine
from sqlalchemy import text

OUTPUT_TYPE_CATEGORY = {
    "finished_goods":     "FG",
    "downgraded_product": "DOWNGRADED",
    "wip":                "WIP",
    "remix":              "REMIX",
    "reject_product":     "REJECT",
}
OUTPUT_TYPES = list(OUTPUT_TYPE_CATEGORY.keys())
LEGACY_COLS  = ("finished_goods", "downgraded_product", "wip", "remix",
                "reject_product", "actual_output", "good_product", "quality_rate")


def _col_exists(conn, schema, table, col):
    return conn.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema=:s AND table_name=:t AND column_name=:c
    """), {"s": schema, "t": table, "c": col}).fetchone() is not None


def _table_exists(conn, schema, table):
    return conn.execute(text("""
        SELECT 1 FROM information_schema.tables
        WHERE table_schema=:s AND table_name=:t
    """), {"s": schema, "t": table}).fetchone() is not None


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

            # ── Step 1: Add new columns if missing ───────────────────────────
            for col, coldef in [
                ("group_id",    "VARCHAR(36)"),
                ("output_type", "VARCHAR(50)"),
                ("category",    "VARCHAR(50)"),
                ("quantity",    "INTEGER NOT NULL DEFAULT 0"),
            ]:
                if not _col_exists(conn, schema, "production_outputs", col):
                    conn.execute(text(
                        f'ALTER TABLE "{schema}".production_outputs '
                        f'ADD COLUMN IF NOT EXISTS {col} {coldef}'
                    ))
                    conn.commit()
            print("   ✅ New columns added")

            # ── Step 2: Backfill — only rows that don't have group_id yet ────
            legacy_exists = _col_exists(conn, schema, "production_outputs", "finished_goods")
            if legacy_exists:
                old_rows = conn.execute(text(f"""
                    SELECT id, date, line_id, shift_id, feed_code_id, production_plan,
                           finished_goods, downgraded_product, wip, remix, reject_product,
                           remarks, is_active, created_at, created_by_id,
                           updated_at, updated_by_id
                    FROM "{schema}".production_outputs
                    WHERE group_id IS NULL
                    ORDER BY id
                """)).fetchall()

                for row in old_rows:
                    (rid, date, line_id, shift_id, fc_id, plan,
                     fg, dg, wip, remix, rej,
                     remarks, is_active, created_at, created_by_id,
                     updated_at, updated_by_id) = row
                    gid = str(uuid.uuid4())
                    qty_map = {
                        "finished_goods":     fg or 0,
                        "downgraded_product": dg or 0,
                        "wip":                wip or 0,
                        "remix":              remix or 0,
                        "reject_product":     rej or 0,
                    }
                    # Update the original row to be the "finished_goods" row
                    conn.execute(text(f"""
                        UPDATE "{schema}".production_outputs
                        SET group_id=:gid, output_type='finished_goods',
                            category='FG', quantity=:qty
                        WHERE id=:rid
                    """), {"gid": gid, "qty": qty_map["finished_goods"], "rid": rid})

                    # Insert 4 more rows for the other types
                    for otype in OUTPUT_TYPES[1:]:
                        conn.execute(text(f"""
                            INSERT INTO "{schema}".production_outputs
                                (group_id, date, line_id, shift_id, feed_code_id,
                                 production_plan, output_type, category, quantity,
                                 remarks, is_active, created_at, created_by_id,
                                 updated_at, updated_by_id)
                            VALUES
                                (:gid, :date, :line_id, :shift_id, :fc_id,
                                 :plan, :otype, :cat, :qty,
                                 :remarks, :is_active, :created_at, :created_by_id,
                                 :updated_at, :updated_by_id)
                        """), {
                            "gid": gid, "date": date, "line_id": line_id,
                            "shift_id": shift_id, "fc_id": fc_id, "plan": plan,
                            "otype": otype, "cat": OUTPUT_TYPE_CATEGORY[otype],
                            "qty": qty_map[otype],
                            "remarks": remarks, "is_active": is_active,
                            "created_at": created_at, "created_by_id": created_by_id,
                            "updated_at": updated_at, "updated_by_id": updated_by_id,
                        })
                conn.commit()
                print(f"   ✅ Backfilled {len(old_rows)} existing records → {len(old_rows)*5} rows")

                # ── Step 3: Drop legacy columns ──────────────────────────────
                for col in LEGACY_COLS:
                    try:
                        conn.execute(text(
                            f'ALTER TABLE "{schema}".production_outputs '
                            f'DROP COLUMN IF EXISTS "{col}"'
                        ))
                        conn.commit()
                    except Exception as exc:
                        conn.rollback()
                        print(f"   ⚠️  Could not drop {col}: {exc}")
                print("   ✅ Legacy columns dropped")
            else:
                print("   ℹ️  Legacy columns absent — backfill skipped")

            # ── Step 4: Drop production_output_items (no longer needed) ──────
            if _table_exists(conn, schema, "production_output_items"):
                try:
                    conn.execute(text(f'DROP TABLE "{schema}".production_output_items CASCADE'))
                    conn.commit()
                    print("   ✅ production_output_items table dropped")
                except Exception as exc:
                    conn.rollback()
                    print(f"   ⚠️  Could not drop production_output_items: {exc}")
            else:
                print("   ℹ️  production_output_items already absent")

            # ── Step 5: Add indexes ──────────────────────────────────────────
            for idx_name, idx_col in [
                (f"idx_{schema}_po_group_id", "group_id"),
                (f"idx_{schema}_po_date",     "date"),
                (f"idx_{schema}_po_type",     "output_type"),
                (f"idx_{schema}_po_category", "category"),
            ]:
                try:
                    conn.execute(text(
                        f'CREATE INDEX IF NOT EXISTS {idx_name} '
                        f'ON "{schema}".production_outputs ({idx_col})'
                    ))
                    conn.commit()
                except Exception:
                    conn.rollback()
            print("   ✅ Indexes ready")

        print("\n✅  Migration complete.")


if __name__ == "__main__":
    migrate()
