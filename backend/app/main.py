from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.config import settings
from app.middleware.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


# Dölj docs i produktion
_docs = None if settings.ENVIRONMENT == "production" else "/docs"
_redoc = None if settings.ENVIRONMENT == "production" else "/redoc"

app = FastAPI(
    title="Synvinkel API",
    redirect_slashes=False,
    description="Alla har en synvinkel — vi visar vilken.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=_docs,
    redoc_url=_redoc,
)

# Rate limiting
if settings.ENVIRONMENT == "production":
    app.add_middleware(RateLimitMiddleware, default_rpm=60, auth_rpm=10)

# CORS — läs från settings (kommaseparerad lista)
origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.ENVIRONMENT}
