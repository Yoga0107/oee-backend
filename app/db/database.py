from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from sqlalchemy.pool import NullPool
from typing import Generator
from app.core.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_schema_engine(schema_name: str):
    connect_args = {"options": f"-csearch_path={schema_name},public"}
    return create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        pool_pre_ping=True,
        poolclass=NullPool,
    )


def get_schema_session(schema_name: str) -> sessionmaker:
    schema_engine = get_schema_engine(schema_name)
    return sessionmaker(autocommit=False, autoflush=False, bind=schema_engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_plant_db(schema_name: str) -> Generator[Session, None, None]:
    PlantSession = get_schema_session(schema_name)
    db = PlantSession()
    try:
        yield db
    finally:
        db.close()


def create_plant_schema(schema_name: str) -> None:
    with engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        conn.commit()


def drop_plant_schema(schema_name: str) -> None:
    with engine.connect() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        conn.commit()


def init_plant_schema_tables(schema_name: str) -> None:
    """Buat semua tabel plant-specific di schema baru."""
    from app.models.plant_schema import PlantBase
    schema_engine = get_schema_engine(schema_name)
    PlantBase.metadata.create_all(bind=schema_engine)
    # Langsung jalankan migrasi untuk schema baru (pastikan konsisten)
    try:
        from app.db.migrate_plant_schema import migrate_plant_schema
        migrate_plant_schema(schema_name)
    except Exception as e:
        print(f"⚠️  migrate_plant_schema warning: {e}")
