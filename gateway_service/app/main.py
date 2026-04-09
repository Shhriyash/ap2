from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.payments import router as payments_router
from app.core.config import settings
from app.db.models import Base
from app.db.session import engine

app = FastAPI(title=settings.gateway_service_name)
app.include_router(health_router)
app.include_router(payments_router)


@app.on_event("startup")
def startup() -> None:
    # Prototype convenience. In production use managed migrations.
    Base.metadata.create_all(bind=engine)
