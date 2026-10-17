from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    InvalidTransition,
    InvalidWebhookSignature,
    PaymentNotFound,
    TariffNotFound,
)


async def payment_not_found_handler(
    request: Request,
    exc: PaymentNotFound
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": "Payment not found"}
    )


async def tariff_not_found_handler(
    request: Request,
    exc: TariffNotFound
) -> JSONResponse:
    error = RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", "tariff_id"),
                "msg": "Tariff does not exist",
                "input": exc.tariff_id,
            }
        ]
    )
    return await request_validation_exception_handler(request, error)


async def invalid_transition_handler(
    request: Request,
    exc: InvalidTransition
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": "invalid_transition"}
    )


async def invalid_signature_handler(
    request: Request,
    exc: InvalidWebhookSignature
) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": "Invalid webhook signature"}
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PaymentNotFound, payment_not_found_handler)
    app.add_exception_handler(TariffNotFound, tariff_not_found_handler)
    app.add_exception_handler(InvalidTransition, invalid_transition_handler)
    app.add_exception_handler(
        InvalidWebhookSignature,
        invalid_signature_handler
    )
