from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import (
    validation_exception_handler,
    integrity_error_handler,
    generic_exception_handler,
)
from app.api.ai.chat import router as ai_chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀  {settings.APP_NAME} v{settings.APP_VERSION} started")

    # ── Migrasi plant schema (sudah ada sebelumnya) ────────────────────────
    try:
        from app.db.migrate_plant_schema import run_all_migrations
        run_all_migrations()
    except Exception as e:
        print(f"⚠️  Migration warning (non-fatal): {e}")

    # ── NEW: Buat tabel AI jika belum ada ─────────────────────────────────
    try:
        from app.db.database import engine, Base
        # Import model agar Base tahu tabel apa yang harus dibuat
        from app.models.ai_models import Conversation, Message, ProviderLog, TokenUsage
        Base.metadata.create_all(bind=engine)
        print("✅  AI tables ready")
    except Exception as e:
        print(f"⚠️  AI table creation warning: {e}")

    yield
    print("👋  Server shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## OEE (Overall Equipment Effectiveness) Backend System

### Autentikasi
1. `POST /api/v1/auth/login` — dapatkan access token & refresh token
2. Sertakan header `Authorization: Bearer <access_token>` di setiap request
3. Sertakan header `X-Plant-ID: <plant_id>` untuk endpoint master data

### Role & Akses
- **administrator / superuser** — akses penuh ke semua plant
- **plant_manager / operator / viewer** — hanya plant yang di-assign
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://dp-enterprise.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(IntegrityError, integrity_error_handler)
app.add_exception_handler(Exception, generic_exception_handler)

app.include_router(api_router)
app.include_router(ai_chat_router)


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION, "docs": "/docs"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}
