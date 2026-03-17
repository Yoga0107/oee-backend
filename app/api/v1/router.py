from fastapi import APIRouter
from app.api.v1.endpoints import auth, plants, master, users

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(plants.router)
api_router.include_router(users.router)
api_router.include_router(master.router)
