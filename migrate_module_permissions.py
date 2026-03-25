"""
migrate_module_permissions.py
Run once to create the user_module_permissions table.

Usage:
    python migrate_module_permissions.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import engine
from sqlalchemy import text

def migrate():
    print("🔄  Running migration: user_module_permissions ...")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.user_module_permissions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                module VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                created_by_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
                CONSTRAINT uq_user_module UNIQUE (user_id, module)
            );
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_user_module_permissions_user_id
            ON public.user_module_permissions (user_id);
        """))
        conn.commit()
    print("✅  Table public.user_module_permissions created (or already exists).")

if __name__ == "__main__":
    migrate()
