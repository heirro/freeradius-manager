"""
RadiusManager API — FastAPI application entry point.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import get_settings
from api.routers import radius, database


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"[INFO] {settings.api_title} v{settings.api_version} starting…")
    if settings.debug:
        print(f"[WARN] Debug mode ON — disable in production!")
    yield
    print("[INFO] Shutting down…")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description="REST API untuk manajemen FreeRADIUS & database MariaDB.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS — sesuaikan origins di production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["X-API-Key", "Content-Type"],
    )

    # Routers
    app.include_router(radius.router, prefix="/api/v1/radius", tags=["FreeRADIUS"])
    app.include_router(database.router, prefix="/api/v1/database", tags=["Database"])

    @app.get("/", include_in_schema=False)
    async def root():
        return JSONResponse({"status": "ok", "message": "RadiusManager API is running"})

    @app.get("/healthz", include_in_schema=False)
    async def health():
        return JSONResponse({"status": "healthy"})

    return app


app = create_app()
