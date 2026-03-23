from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import (
    ALLOWED_ORIGINS,
    API_PREFIX,
    API_VERSION,
    APP_CONTACT,
    APP_DESCRIPTION,
    APP_LICENSE,
    APP_TITLE,
)
from api.routes import email, gaia, drive, geolocate, session, spiderdal


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize GHunt globals on startup."""
    from ghunt import globals as gb
    gb.init_globals()
    yield


app = FastAPI(
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version=API_VERSION,
    contact=APP_CONTACT,
    license_info=APP_LICENSE,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Global Exception Handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )


# --- Health Check (no auth required) ---
@app.get(
    "/health",
    tags=["System"],
    summary="Health check",
    description="Check if the API is running. No authentication required.",
)
async def health():
    return {"status": "ok", "version": API_VERSION, "api": APP_TITLE}


# --- Root ---
@app.get(
    "/",
    tags=["System"],
    summary="API info",
    description="Returns basic API info and links to documentation.",
    include_in_schema=False,
)
async def root():
    return {
        "name": APP_TITLE,
        "version": API_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }


# --- Register routers ---
app.include_router(session.router, prefix=API_PREFIX)
app.include_router(email.router, prefix=API_PREFIX)
app.include_router(gaia.router, prefix=API_PREFIX)
app.include_router(drive.router, prefix=API_PREFIX)
app.include_router(geolocate.router, prefix=API_PREFIX)
app.include_router(spiderdal.router, prefix=API_PREFIX)
