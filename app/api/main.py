from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.api.routes.app_routes import app_router
from app.api.routes.auth_routes import auth_router
from app.api.routes.admin_routes import admin_router
from app.api.routes.result_routes import results_router
from app.api.routes.predictions_routes import predictions_router
from app.db.database import init_indexes, db

from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan, root_path=settings.ROOT_PATH)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await init_indexes()
    # also load all required cache in prod
    yield
    # shutdown
    db.client.close()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change in production, take from env
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(app_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(results_router)
app.include_router(predictions_router)

# slowapi removed here, only present in prev version of skeleton

@app.get("/health")
def health():
    return {"status": "ok"}
