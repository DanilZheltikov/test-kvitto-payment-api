from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.exception_handlers import register_exception_handlers
from app.api.routers import api_router
from app.core.config import settings
from app.db.session import engine, session_factory
from app.services.tariffs import tariff_service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    try:
        if not settings.webhook_secret.get_secret_value():
            raise RuntimeError(
                "Set a nonempty WEBHOOK_SECRET before starting the API"
            )
        async with session_factory() as session:
            await tariff_service.seed(session)
        yield
    finally:
        await engine.dispose()


app = FastAPI(title="Kvitto Payment API", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(api_router)
