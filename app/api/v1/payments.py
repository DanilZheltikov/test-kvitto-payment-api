from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status
from pydantic import EmailStr

from app.api.dependencies import IdempotencyKey, SessionDep
from app.api.docs import PAYMENT_CREATE_RESPONSES, PAYMENT_GET_RESPONSES
from app.models.payment import Payment
from app.schemas.payment import PaymentCreate, PaymentRead
from app.schemas.types import PaymentStatus
from app.services.payments import payment_service


router = APIRouter(prefix="/payments")


@router.post(
    "",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    responses=PAYMENT_CREATE_RESPONSES
)
async def create_payment(
    data: PaymentCreate,
    response: Response,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> Payment:
    payment, created = await payment_service.create(
        session=session,
        data=data,
        idempotency_key=idempotency_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return payment


@router.get("", response_model=list[PaymentRead])
async def list_payments(
    session: SessionDep,
    email: Annotated[EmailStr | None, Query()] = None,
    status: Annotated[PaymentStatus | None, Query()] = None,
) -> list[Payment]:
    return await payment_service.list(session, email=email, status=status)


@router.get(
    "/{payment_id}",
    response_model=PaymentRead,
    responses=PAYMENT_GET_RESPONSES,
)
async def get_payment(
    payment_id: UUID,
    session: SessionDep,
) -> Payment:
    return await payment_service.get_by_id(session, payment_id)
