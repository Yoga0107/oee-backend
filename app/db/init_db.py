"""
Run once to initialise the public schema tables and seed default data.
Usage:  python -m app.db.init_db
"""
from app.db.database import engine, Base
from sqlalchemy import text
from app.models.public import Role, User, Plant, UserPlant, RefreshToken  # noqa: F401
from app.core.security import get_password_hash
from sqlalchemy.orm import Session


def init_db() -> None:
    # Create all public-schema tables
    Base.metadata.create_all(bind=engine)
    print("✅  Public schema tables created.")

    with Session(engine) as db:
        # Guard: add must_change_password column if it doesn't exist (migration for existing DBs)
        try:
            db.execute(text("""
                ALTER TABLE public.users
                    ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE;
            """))
            db.commit()
        except Exception:
            db.rollback()

    with Session(engine) as db:
        # Seed roles if not present
        default_roles = [
            {"name": "administrator", "description": "Full system access"},
            {"name": "plant_manager", "description": "Manage a single plant"},
            {"name": "operator", "description": "Input OEE data"},
            {"name": "viewer", "description": "Read-only access"},
        ]
        for role_data in default_roles:
            exists = db.query(Role).filter(Role.name == role_data["name"]).first()
            if not exists:
                db.add(Role(**role_data))
        db.flush()

        admin_role = db.query(Role).filter(Role.name == "administrator").first()

        # Seed superuser if not present
        superuser = db.query(User).filter(User.username == "admin").first()
        if not superuser:
            db.add(
                User(
                    username="admin",
                    email="admin@oee.local",
                    full_name="System Administrator",
                    hashed_password=get_password_hash("Admin@1234"),
                    role_id=admin_role.id,
                    is_superuser=True,
                )
            )
            print("✅  Default superuser created  →  username: admin / password: Admin@1234")

        db.commit()
        print("✅  Seed data committed.")


if __name__ == "__main__":
    init_db()
