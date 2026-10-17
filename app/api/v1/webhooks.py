from fastapi import APIRouter, Depends

from app.api.dependencies import SessionDep, verify_bank_signature
from app.api.docs import BANK_WEBHOOK_RESPONSES
from app.schemas.webhook import BankWebhook, WebhookResponse
from app.services.payments import payment_service


router = APIRouter(prefix="/webhooks")


@router.post(
    "/bank",
    response_model=WebhookResponse,
    dependencies=[Depends(verify_bank_signature)],
    responses=BANK_WEBHOOK_RESPONSES
)
async def bank_webhook(
    data: BankWebhook,
    session: SessionDep,
) -> WebhookResponse:
    await payment_service.change_status(session, data.payment_id, data.status)
    return WebhookResponse()
