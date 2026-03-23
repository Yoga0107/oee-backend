import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    # --- Database Configuration ---
    # Gunakan Optional atau default None jika variabel ini 
    # akan dibentuk otomatis di sistem tertentu
    DB_HOST: str
    DB_PORT: str 
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DATABASE_URL: str

    # --- Security & JWT ---
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7 # Saran: Jangan disamakan dengan menit (480 hari terlalu lama)

    # --- App Configuration ---
    APP_NAME: str = "OEE Backend API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # --- Google SSO ---
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET")
    ALLOWED_EMAIL_DOMAIN: str = os.getenv("ALLOWED_EMAIL_DOMAIN", "cpp.co.id") 
    # --- Pydantic Config ---
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8", # Tambahan agar aman di Windows (Yoga.Putra@2-01-00797)
        extra="ignore",
        case_sensitive=False # Agar DB_HOST atau db_host di .env sama-sama terbaca
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()