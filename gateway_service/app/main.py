import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes.auth_context import router as auth_context_router
from app.api.routes.health import router as health_router
from app.api.routes.onboarding import router as onboarding_router
from app.api.routes.payments import router as payments_router
from app.api.routes.users import router as users_router
from app.core.config import settings
from app.core.gateway_logger import log_event
from app.core.request_context import set_correlation_id
from app.db.models import Base
from app.db.session import SessionLocal, engine

app = FastAPI(title=settings.gateway_service_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(auth_context_router)
app.include_router(onboarding_router)
app.include_router(payments_router)
app.include_router(users_router)


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or f"corr_{uuid4().hex}"
    set_correlation_id(correlation_id)
    started = time.time()
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    duration_ms = int((time.time() - started) * 1000)
    log_event(
        "http_request",
        {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.on_event("startup")
def startup() -> None:
    # Prototype convenience. In production use managed migrations.
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS pin_hash TEXT"))
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT"))
        db.commit()
