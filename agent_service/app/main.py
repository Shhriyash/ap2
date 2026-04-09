from fastapi import FastAPI

from app.api.routes.agent import router as agent_router
from app.api.routes.health import router as health_router
from app.core.config import settings

app = FastAPI(title=settings.agent_service_name)
app.include_router(health_router)
app.include_router(agent_router)
