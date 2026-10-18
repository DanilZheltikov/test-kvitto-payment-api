import hashlib
import hmac
import json
from uuid import UUID

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.tariff import Tariff
from app.schemas.types import PaymentMethod, PaymentStatus


WEBHOOK_URL = "/api/v1/webhooks/bank"
TARIFF_TITLE = "standard"
TEST_EMAIL = "customer@example.com"
PAYMENT_AMOUNT = 1_990_000
MISSING_PAYMENT_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
async def payment(db_session: AsyncSession) -> Payment:
    tariff = (
        await db_session.scalars(
            select(Tariff).where(Tariff.title == TARIFF_TITLE)
        )
    ).one()
    payment = Payment(
        tariff_id=tariff.id,
        email=TEST_EMAIL,
        method=PaymentMethod.CARD,
        status=PaymentStatus.PENDING,
        amount=PAYMENT_AMOUNT,
        discount=0,
    )
    db_session.add(payment)
    await db_session.commit()
    return payment


def build_signed_webhook(
    payment_id: UUID,
    target_status: str,
    secret: str,
) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(
        {"payment_id": str(payment_id), "status": target_status},
        separators=(",", ":"),
    ).encode("utf-8")
    signature = hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256,
    ).hexdigest()
    return body, {
        "Content-Type": "application/json",
        "X-Signature": signature,
    }


async def assert_payment_status(
    db_session: AsyncSession,
    payment_id: UUID,
    expected_status: str,
) -> None:
    stored_payment = await db_session.get(
        Payment, payment_id, populate_existing=True,
    )
    assert stored_payment is not None, (
        f"Payment {payment_id} must still exist after the webhook"
    )
    assert stored_payment.status == expected_status, (
        f"Payment {payment_id}: expected stored status {expected_status!r}, "
        f"got {stored_payment.status.value!r}"
    )


@pytest.mark.parametrize(
    ("initial_status", "target_status"),
    [
        pytest.param("pending", "succeeded", id="pending-to-succeeded"),
        pytest.param("pending", "failed", id="pending-to-failed"),
        pytest.param("succeeded", "refunded", id="succeeded-to-refunded"),
    ],
)
async def test_webhook_allows_status_transition(
    client: AsyncClient,
    db_session: AsyncSession,
    payment: Payment,
    webhook_secret: str,
    initial_status: str,
    target_status: str,
) -> None:

    payment.status = PaymentStatus(initial_status)

    await db_session.commit()

    body, headers = build_signed_webhook(
        payment_id=payment.id,
        target_status=target_status,
        secret=webhook_secret,
    )

    response = await client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == status.HTTP_200_OK, (
        f"Payment {payment.id}: allowed transition "
        f"{initial_status!r} -> {target_status!r} must return 200; "
        f"got {response.status_code}. Response: {response.text}"
    )
    assert response.json() == {"result": "ok"}, (
        f"Payment {payment.id}: unexpected response for an allowed transition"
    )
    await assert_payment_status(db_session, payment.id, target_status)


@pytest.mark.parametrize(
    ("initial_status", "target_status"),
    [
        pytest.param("pending", "refunded", id="pending-to-refunded"),
        pytest.param("succeeded", "pending", id="succeeded-to-pending"),
        pytest.param("succeeded", "failed", id="succeeded-to-failed"),
        pytest.param("failed", "pending", id="failed-to-pending"),
        pytest.param("failed", "succeeded", id="failed-to-succeeded"),
        pytest.param("failed", "refunded", id="failed-to-refunded"),
        pytest.param("refunded", "pending", id="refunded-to-pending"),
        pytest.param("refunded", "succeeded", id="refunded-to-succeeded"),
        pytest.param("refunded", "failed", id="refunded-to-failed"),
    ],
)
async def test_webhook_rejects_forbidden_status_transition(
    client: AsyncClient,
    db_session: AsyncSession,
    payment: Payment,
    webhook_secret: str,
    initial_status: str,
    target_status: str,
) -> None:
    payment.status = PaymentStatus(initial_status)
    await db_session.commit()
    body, headers = build_signed_webhook(
        payment_id=payment.id,
        target_status=target_status,
        secret=webhook_secret,
    )

    response = await client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == status.HTTP_409_CONFLICT, (
        f"Payment {payment.id}: forbidden transition "
        f"{initial_status!r} -> {target_status!r} must return 409; "
        f"got {response.status_code}. Response: {response.text}"
    )
    assert response.json() == {"error": "invalid_transition"}, (
        f"Payment {payment.id}: unexpected error for a forbidden transition"
    )
    await assert_payment_status(db_session, payment.id, initial_status)


@pytest.mark.parametrize(
    "current_status", ["pending", "succeeded", "failed", "refunded"],
)
async def test_webhook_rejects_current_status(
    client: AsyncClient,
    db_session: AsyncSession,
    payment: Payment,
    webhook_secret: str,
    current_status: str,
) -> None:
    payment.status = PaymentStatus(current_status)
    await db_session.commit()

    body, headers = build_signed_webhook(
        payment_id=payment.id,
        target_status=current_status,
        secret=webhook_secret,
    )

    response = await client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == status.HTTP_409_CONFLICT, (
        f"Payment {payment.id}: repeating current status {current_status!r} "
        f"must return 409; got {response.status_code}. "
        f"Response: {response.text}"
    )
    assert response.json() == {"error": "invalid_transition"}, (
        f"Payment {payment.id}: unexpected error when repeating current status"
    )
    await assert_payment_status(db_session, payment.id, current_status)


async def test_webhook_rejects_missing_payment(
    client: AsyncClient,
    db_session: AsyncSession,
    webhook_secret: str,
) -> None:
    body, headers = build_signed_webhook(
        payment_id=MISSING_PAYMENT_ID,
        target_status="succeeded",
        secret=webhook_secret,
    )

    response = await client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND, (
        f"Webhook for missing payment {MISSING_PAYMENT_ID} must return 404; "
        f"got {response.status_code}. Response: {response.text}"
    )
    assert response.json() == {"detail": "Payment not found"}, (
        f"Missing payment {MISSING_PAYMENT_ID}: unexpected error response"
    )

    payment_count = await db_session.scalar(
        select(func.count()).select_from(Payment)
    )

    assert payment_count == 0, (
        "A webhook for a missing payment must not create a payment; "
        f"found {payment_count} record(s) in the database"
    )
