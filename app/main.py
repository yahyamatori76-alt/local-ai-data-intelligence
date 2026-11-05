"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes_analysis import router as analysis_router
from app.api.routes_chat import router as chat_router
from app.api.routes_health import router as health_router
from app.api.routes_import import router as import_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_documents import router as documents_router
from app.db.bootstrap import initialize_database
from app.db.repositories import get_engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database(get_engine())
    yield


app = FastAPI(
    title="Local AI Data Intelligence Platform",
    version="0.2.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(import_router)
app.include_router(analysis_router)
app.include_router(chat_router)
app.include_router(dashboard_router)
app.include_router(documents_router)
