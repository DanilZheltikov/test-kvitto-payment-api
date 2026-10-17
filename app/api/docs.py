from fastapi import status

from app.schemas.payment import PaymentRead
from app.schemas.webhook import InvalidTransitionResponse

BANK_WEBHOOK_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid signature"
    },
    status.HTTP_404_NOT_FOUND: {"description": "Payment not found"},
    status.HTTP_409_CONFLICT: {"model": InvalidTransitionResponse},
}

PAYMENT_CREATE_RESPONSES = {
    status.HTTP_200_OK: {
        "model": PaymentRead,
        "description": "Existing payment"
    },
}

PAYMENT_GET_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {"description": "Payment not found"},
}
