"""
migrate_output_items.py
Creates production_output_items table in every active plant schema,
then backfills existing production_outputs rows.

Run once:
    python migrate_output_items.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import engine
from sqlalchemy import text

OUTPUT_TYPES = ("finished_goods", "downgraded_product", "wip", "remix", "reject_product")


def migrate():
    with engine.connect() as conn:
        # 1. Fetch all plant schemas
        schemas = conn.execute(text(
            "SELECT schema_name FROM public.plants WHERE is_active = TRUE"
        )).fetchall()

        if not schemas:
            print("⚠️  No active plants found — nothing to migrate.")
            return

        for (schema,) in schemas:
            print(f"\n🔄  Schema: {schema}")

            # 2. Create table if not exists
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {schema}.production_output_items (
                    id          SERIAL PRIMARY KEY,
                    output_id   INTEGER NOT NULL
                                  REFERENCES {schema}.production_outputs(id)
                                  ON DELETE CASCADE,
                    output_type VARCHAR(50) NOT NULL,
                    quantity    INTEGER NOT NULL DEFAULT 0,
                    created_at  TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT uq_{schema}_output_item UNIQUE (output_id, output_type)
                );
            """))
            conn.execute(text(f"""
                CREATE INDEX IF NOT EXISTS idx_{schema}_poi_output_id
                ON {schema}.production_output_items (output_id);
            """))
            conn.execute(text(f"""
                CREATE INDEX IF NOT EXISTS idx_{schema}_poi_type
                ON {schema}.production_output_items (output_type);
            """))
            print(f"   ✅ Table created (or already exists)")

            # 3. Backfill existing rows
            for otype in OUTPUT_TYPES:
                conn.execute(text(f"""
                    INSERT INTO {schema}.production_output_items (output_id, output_type, quantity)
                    SELECT id, :otype, COALESCE({otype}, 0)
                    FROM {schema}.production_outputs
                    WHERE is_active = TRUE
                    ON CONFLICT (output_id, output_type) DO UPDATE
                        SET quantity = EXCLUDED.quantity;
                """), {"otype": otype})
            print(f"   ✅ Backfilled existing rows for {len(OUTPUT_TYPES)} types")

        conn.commit()
        print("\n✅  Migration complete.")


if __name__ == "__main__":
    migrate()
