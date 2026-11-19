from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import OperationalError
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings
from app.db import get_engine, init_engine
from app.logging import setup_logging
from app.models import Base
from app.routes import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine(settings.database_url)
    Base.metadata.create_all(bind=get_engine())
    yield


app = FastAPI(title="Sample Sentinel", lifespan=lifespan)
app.include_router(router)


@app.exception_handler(OperationalError)
async def operational_error_handler(_request: Request, _exc: OperationalError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "database unavailable"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
