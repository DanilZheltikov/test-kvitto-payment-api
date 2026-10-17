from fastapi import APIRouter

from app.api.v1 import payments, tariffs, webhooks


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(tariffs.router, tags=["Tariffs"])
api_router.include_router(payments.router, tags=["Payments"])
api_router.include_router(webhooks.router, tags=["Webhooks"])
