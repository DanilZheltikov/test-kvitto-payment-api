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
MISSING_PAYMENT_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
async def payment(db_session: AsyncSession) -> Payment:
    tariff = (
        await db_session.scalars(
            select(Tariff).where(Tariff.title == "standard")
        )
    ).one()
    payment = Payment(
        tariff_id=tariff.id,
        email="customer@example.com",
        method=PaymentMethod.CARD,
        status=PaymentStatus.PENDING,
        amount=1_990_000,
        discount=0,
    )
    db_session.add(payment)
    await db_session.commit()
    return payment


@pytest.fixture
def payment_snapshot(payment: Payment) -> dict[str, object]:
    return {
        column.name: getattr(payment, column.name)
        for column in Payment.__table__.columns
    }


def signed_payload(
    payload: dict[str, str], secret: str
) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, {
        "Content-Type": "application/json",
        "X-Signature": signature,
    }


def signed_webhook(
    payment_id: UUID, target_status: str, secret: str
) -> tuple[bytes, dict[str, str]]:
    return signed_payload(
        {"payment_id": str(payment_id), "status": target_status}, secret
    )


async def assert_stored_status(
    session: AsyncSession, payment_id: UUID, expected: PaymentStatus
) -> None:
    payment = await session.get(Payment, payment_id, populate_existing=True)
    assert payment is not None
    assert payment.status == expected


async def assert_payment_unchanged(
    session: AsyncSession,
    payment_id: UUID,
    snapshot: dict[str, object],
) -> None:
    payment = await session.get(Payment, payment_id, populate_existing=True)
    assert payment is not None
    assert {
        name: getattr(payment, name) for name in snapshot
    } == snapshot
    assert await session.scalar(select(func.count()).select_from(Payment)) == 1


@pytest.mark.parametrize(
    ("initial", "target"),
    [
        (PaymentStatus.PENDING, PaymentStatus.SUCCEEDED),
        (PaymentStatus.PENDING, PaymentStatus.FAILED),
        (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED),
    ],
)
async def test_webhook_allows_status_transition(
    client: AsyncClient,
    db_session: AsyncSession,
    payment: Payment,
    webhook_secret: str,
    initial: PaymentStatus,
    target: PaymentStatus,
) -> None:
    payment.status = initial
    await db_session.commit()

    body, headers = signed_webhook(payment.id, target.value, webhook_secret)
    response = await client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"result": "ok"}
    await assert_stored_status(db_session, payment.id, target)


@pytest.mark.parametrize(
    ("initial", "target"),
    [
        (PaymentStatus.PENDING, PaymentStatus.REFUNDED),
        (PaymentStatus.SUCCEEDED, PaymentStatus.PENDING),
        (PaymentStatus.SUCCEEDED, PaymentStatus.FAILED),
        (PaymentStatus.FAILED, PaymentStatus.PENDING),
        (PaymentStatus.FAILED, PaymentStatus.SUCCEEDED),
        (PaymentStatus.FAILED, PaymentStatus.REFUNDED),
        (PaymentStatus.REFUNDED, PaymentStatus.PENDING),
        (PaymentStatus.REFUNDED, PaymentStatus.SUCCEEDED),
        (PaymentStatus.REFUNDED, PaymentStatus.FAILED),
    ],
)
async def test_webhook_rejects_forbidden_status_transition(
    client: AsyncClient,
    db_session: AsyncSession,
    payment: Payment,
    webhook_secret: str,
    initial: PaymentStatus,
    target: PaymentStatus,
) -> None:
    payment.status = initial
    await db_session.commit()

    body, headers = signed_webhook(payment.id, target.value, webhook_secret)
    response = await client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {"error": "invalid_transition"}
    await assert_stored_status(db_session, payment.id, initial)


@pytest.mark.parametrize("current", list(PaymentStatus))
async def test_webhook_rejects_current_status(
    client: AsyncClient,
    db_session: AsyncSession,
    payment: Payment,
    webhook_secret: str,
    current: PaymentStatus,
) -> None:
    payment.status = current
    await db_session.commit()

    body, headers = signed_webhook(payment.id, current.value, webhook_secret)
    response = await client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {"error": "invalid_transition"}
    await assert_stored_status(db_session, payment.id, current)


async def test_webhook_rejects_missing_payment(
    client: AsyncClient, db_session: AsyncSession, webhook_secret: str
) -> None:
    body, headers = signed_webhook(
        MISSING_PAYMENT_ID, PaymentStatus.SUCCEEDED.value, webhook_secret
    )
    response = await client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Payment not found"}
    assert await db_session.scalar(
        select(func.count())
        .select_from(Payment)
    ) == 0


@pytest.mark.parametrize(
    "signature_header",
    [None, "", "0" * 64],
    ids=["missing", "empty", "incorrect"],
)
async def test_webhook_rejects_invalid_signature(
    client: AsyncClient,
    db_session: AsyncSession,
    payment: Payment,
    payment_snapshot: dict[str, object],
    webhook_secret: str,
    signature_header: str | None,
) -> None:
    body, headers = signed_webhook(
        payment.id, PaymentStatus.SUCCEEDED.value, webhook_secret
    )
    if signature_header is None:
        del headers["X-Signature"]
    else:
        headers["X-Signature"] = signature_header

    response = await client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Invalid webhook signature"}
    await assert_payment_unchanged(db_session, payment.id, payment_snapshot)


async def test_webhook_rejects_body_changed_after_signing(
    client: AsyncClient,
    db_session: AsyncSession,
    payment: Payment,
    payment_snapshot: dict[str, object],
    webhook_secret: str,
) -> None:
    body, headers = signed_webhook(
        payment.id, PaymentStatus.SUCCEEDED.value, webhook_secret
    )
    changed_body = body.replace(b'"succeeded"', b'"failed"')
    assert changed_body != body

    response = await client.post(
        WEBHOOK_URL, content=changed_body, headers=headers
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Invalid webhook signature"}
    await assert_payment_unchanged(db_session, payment.id, payment_snapshot)


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    [
        ("payment_id", "not-a-uuid", "uuid_parsing"),
        ("status", "unknown", "enum"),
    ],
)
async def test_webhook_rejects_invalid_field(
    client: AsyncClient,
    db_session: AsyncSession,
    payment: Payment,
    payment_snapshot: dict[str, object],
    webhook_secret: str,
    field: str,
    value: str,
    error_type: str,
) -> None:
    payload = {"payment_id": str(payment.id), "status": "succeeded"}
    payload[field] = value
    body, headers = signed_payload(payload, webhook_secret)

    response = await client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert any(
        error["loc"] == ["body", field] and error["type"] == error_type
        for error in response.json()["detail"]
    )
    await assert_payment_unchanged(db_session, payment.id, payment_snapshot)


@pytest.mark.parametrize("field", ["payment_id", "status"])
async def test_webhook_requires_field(
    client: AsyncClient,
    db_session: AsyncSession,
    payment: Payment,
    payment_snapshot: dict[str, object],
    webhook_secret: str,
    field: str,
) -> None:
    payload = {"payment_id": str(payment.id), "status": "succeeded"}
    del payload[field]
    body, headers = signed_payload(payload, webhook_secret)

    response = await client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert any(
        error["loc"] == ["body", field] and error["type"] == "missing"
        for error in response.json()["detail"]
    )
    await assert_payment_unchanged(db_session, payment.id, payment_snapshot)
