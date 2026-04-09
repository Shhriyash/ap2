import time
from uuid import uuid4

from fastapi import FastAPI, Request

from app.api.routes.agent import router as agent_router
from app.api.routes.health import router as health_router
from app.core.agent_logger import log_event
from app.core.request_context import set_correlation_id
from app.core.config import settings

app = FastAPI(title=settings.agent_service_name)
app.include_router(health_router)
app.include_router(agent_router)


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
