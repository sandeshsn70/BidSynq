"""BidSynq API entry point (``uvicorn app.main:app``)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings, validate_production_settings
from app.database import SessionLocal
from app.routers import audit, auth, documents, intelligence, risk, tenders
from app.schemas import HealthOut

VERSION = "5.1.0"
logger = logging.getLogger("bidsynq")


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_production_settings()
    # Tables are created and changed ONLY by Alembic migrations (see docs/DEPLOYMENT.md).
    # The application itself never creates or drops tables.
    yield


app = FastAPI(
    title="BidSynq API",
    version=VERSION,
    description="B2B procurement with RAG, supplier intelligence, risk review and tamper-evident audit trails",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,  # Bearer tokens are sent in a header; cookies are not used.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/health", response_model=HealthOut, tags=["system"])
def health():
    """Liveness + dependency check. Returns 200 even if the database is down so Render does not
    restart-loop the service; read the ``database`` field to see the real state."""
    database, revision = "ok", None
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            try:
                revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
            except Exception:
                db.rollback()
                revision = None
    except Exception:
        logger.exception("Health check could not reach the database")
        database = "unavailable"
    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        version=VERSION,
        database=database,
        migration_revision=revision,
        rag="enabled",
        groq_configured=bool(settings.groq_api_key),
        supplier_intelligence="enabled",
        price_intelligence="advisory",
        risk_monitoring="human_review_only",
        audit_chain="enabled",
    )


for module in (auth, tenders, documents, intelligence, risk, audit):
    app.include_router(module.router)
