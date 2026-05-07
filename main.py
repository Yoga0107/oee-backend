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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup: jalankan migrasi semua plant schema ───────────────────────
    print(f"🚀  {settings.APP_NAME} v{settings.APP_VERSION} started")
    try:
        from app.db.migrate_plant_schema import run_all_migrations
        run_all_migrations()
    except Exception as e:
        print(f"⚠️  Migration warning (non-fatal): {e}")
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
    allow_origins=["http://localhost:3000",
                   "http://localhost:3001",
        "https://dp-enterprise.vercel.app",],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(IntegrityError, integrity_error_handler)
app.add_exception_handler(Exception, generic_exception_handler)

app.include_router(api_router)


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION, "docs": "/docs"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}
